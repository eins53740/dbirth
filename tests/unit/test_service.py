import json
import threading
import pytest
import sys
import types
import unittest
import uns_metadata_sync.service as service
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uns_metadata_sync import sparkplug_b_pb2 as sparkplug
from uns_metadata_sync.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

if "paho" not in sys.modules:
    paho_module = types.ModuleType("paho")
    mqtt_module = types.ModuleType("paho.mqtt")
    mqtt_client_module = types.ModuleType("paho.mqtt.client")

    class _DummyClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    mqtt_client_module.Client = _DummyClient
    mqtt_client_module.CallbackAPIVersion = types.SimpleNamespace(VERSION2="V2")
    mqtt_client_module.MQTTv311 = 4

    sys.modules["paho"] = paho_module
    sys.modules["paho.mqtt"] = mqtt_module
    sys.modules["paho.mqtt.client"] = mqtt_client_module
    mqtt_module.client = mqtt_client_module

if "dotenv" not in sys.modules:
    sys.modules["dotenv"] = types.SimpleNamespace(
        load_dotenv=lambda *args, **kwargs: None
    )


if "dotenv" not in sys.modules:
    sys.modules["dotenv"] = types.SimpleNamespace(
        load_dotenv=lambda *args, **kwargs: None
    )


class StubClient:
    """Minimal stand-in for paho.mqtt.client.Client used in tests."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.username_pw = None
        self.tls_set_context_called = False
        self.tls_insecure_flag = None
        self.subscriptions = []
        self.published = []
        self.connect_args = None
        self.loop_forever_called = False
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None

    def username_pw_set(self, username, password):
        self.username_pw = (username, password)

    def tls_set_context(self):
        self.tls_set_context_called = True

    def tls_insecure_set(self, flag):
        self.tls_insecure_flag = flag

    def subscribe(self, subscriptions):
        self.subscriptions.append(subscriptions)
        return []

    def publish(self, topic, payload=b""):
        self.published.append((topic, payload))
        return types.SimpleNamespace(rc=0)

    def connect(self, host, port, keepalive=60):
        self.connect_args = (host, port, keepalive)

    def loop_forever(self):
        self.loop_forever_called = True


def make_settings(base_path: Path, **overrides) -> Settings:
    base = {
        "broker": "broker.example",
        "port": 8883,
        "username": "user",
        "password": "pass",
        "topic_all": "spBv1.0/Secil/DBIRTH/#",
        "topic_nbirth_all": "spBv1.0/+/NBIRTH/#",
        "topic_dbirth_all": "spBv1.0/+/DBIRTH/#",
        "alias_cache_path": base_path / "alias_cache.json",
        "write_jsonl": False,
        "jsonl_pattern": str(base_path / "messages_{topic}.jsonl"),
        "auto_request_rebirth": True,
        "rebirth_throttle_seconds": 60,
        "client_id": "client-123",
        "tls_insecure": False,
        "db_mode": "mock",
        "db_host": "localhost",
        "db_port": 5432,
        "db_name": "uns_metadata",
        "db_user": "postgres",
        "db_password": "postgres",
        "db_schema": "uns_meta",
        "cdc_enabled": False,
        "cdc_slot": "uns_meta_slot",
        "cdc_publication": "uns_meta_pub",
        "cdc_window_seconds": 180,
        "cdc_flush_interval_seconds": 5.0,
        "cdc_buffer_cap": 1000,
        "cdc_idle_sleep_seconds": 1.0,
        "cdc_max_batch_messages": 500,
        "pg_replication_user": "postgres",
        "pg_replication_password": "postgres",
        "pg_replication_host": "localhost",
        "pg_replication_port": 5432,
        "pg_replication_database": "uns_metadata",
        "pg_replication_sslmode": "prefer",
        "cdc_checkpoint_backend": "memory",
        "cdc_resume_path": base_path / "cdc_resume.json",
        "cdc_resume_fsync": False,
    }
    base.update(overrides)
    return Settings(**base)


def build_metric_with_property(
    name: str, alias: int, datatype: int, prop_key: str, prop_value: str
):
    metric = sparkplug.Payload.Metric()
    metric.name = name
    metric.alias = alias
    metric.datatype = datatype
    props = metric.properties
    props.keys.append(prop_key)
    prop_entry = props.values.add()
    prop_entry.string_value = prop_value
    return metric


def build_dataset_metric(name: str, alias: int) -> sparkplug.Payload.Metric:
    metric = sparkplug.Payload.Metric()
    metric.name = name
    metric.alias = alias
    dataset = metric.dataset_value
    dataset.columns.extend(["pressure", "temperature"])
    first_row = dataset.rows.add()
    first_row.elements.add().int_value = 10
    first_row.elements.add().float_value = 21.5
    second_row = dataset.rows.add()
    second_row.elements.add().int_value = 12
    second_row.elements.add().float_value = 22.1
    return metric


class SparkplugSubscriberTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.tmp_path = Path(self.tempdir.name)
        self.created_clients = []
        self.mqtt_patcher = patch.object(
            service.mqtt, "Client", side_effect=self._client_factory
        )
        self.mqtt_patcher.start()
        self.addCleanup(self.mqtt_patcher.stop)

    def _client_factory(self, *args, **kwargs):
        client = StubClient(*args, **kwargs)
        self.created_clients.append(client)
        return client

    def _make_settings(self, **overrides) -> Settings:
        return make_settings(self.tmp_path, **overrides)

    class SpyRepository:
        def __init__(self):
            self.device_payloads = []
            self.metric_payloads = []
            self.property_payloads = []
            self.conn = self._make_mock_conn()

        def _make_mock_conn(self):
            conn = unittest.mock.MagicMock()
            conn.transaction.return_value = unittest.mock.MagicMock(
                __enter__=unittest.mock.MagicMock(),
                __exit__=unittest.mock.MagicMock(return_value=None),
            )
            return conn

        @staticmethod
        def _result(status: str, record: dict):
            return types.SimpleNamespace(status=status, record=record)

        def upsert_device(self, payload):
            self.device_payloads.append(payload)
            return self._result("inserted", {"device_id": 1})

        def upsert_metrics_bulk(self, payloads, *, batch_size=1000):
            self.metric_payloads.extend(payloads)
            return {p.name: i for i, p in enumerate(payloads, 101)}

        def upsert_metric_properties_bulk(
            self, payloads, *, batch_size=1000, manage_transaction=True
        ):
            self.property_payloads.extend(payloads)
            return len(payloads)

    @pytest.mark.unit
    def test_build_client_configures_tls_and_credentials(self):
        subscriber = service.SparkplugSubscriber(self._make_settings())
        client = subscriber.client

        self.assertEqual(
            client.username_pw,
            (subscriber.settings.username, subscriber.settings.password),
        )
        self.assertTrue(client.tls_set_context_called)
        self.assertIs(client.tls_insecure_flag, subscriber.settings.tls_insecure)
        self.assertEqual(client.kwargs["client_id"], subscriber.settings.client_id)
        self.assertEqual(
            client.kwargs["callback_api_version"],
            service.mqtt.CallbackAPIVersion.VERSION2,
        )
        self.assertEqual(client.kwargs["protocol"], service.mqtt.MQTTv311)
        self.assertIs(client.on_connect.__self__, subscriber)
        self.assertIs(client.on_connect.__func__, subscriber.on_connect.__func__)
        self.assertIs(client.on_message.__self__, subscriber)
        self.assertIs(client.on_message.__func__, subscriber.on_message.__func__)

    @pytest.mark.unit
    def test_connect_invokes_underlying_client(self):
        subscriber = service.SparkplugSubscriber(
            self._make_settings(broker="mqtt.internal", port=8884)
        )

        subscriber.connect()

        self.assertEqual(
            subscriber.client.connect_args,
            (subscriber.settings.broker, subscriber.settings.port, 60),
        )

    @pytest.mark.unit
    def test_on_connect_subscribes_to_expected_topics(self):
        subscriber = service.SparkplugSubscriber(self._make_settings())

        subscriber.on_connect(subscriber.client, None, None, 0)

        expected = [
            [
                (subscriber.settings.topic_all, 0),
                (subscriber.settings.topic_nbirth_all, 0),
                (subscriber.settings.topic_dbirth_all, 0),
            ]
        ]
        self.assertEqual(subscriber.client.subscriptions, expected)

    @pytest.mark.unit
    def test_ingest_birth_records_alias_and_resolves_name(self):
        subscriber = service.SparkplugSubscriber(self._make_settings())

        payload = sparkplug.Payload()
        payload.metrics.extend(
            [build_metric_with_property("pump_state", 7, 1, "unit", "kW")]
        )

        subscriber._ingest_birth("Secil", "EdgeNode", "DeviceA", payload)

        alias_key = ("Secil", "EdgeNode", "DeviceA")
        self.assertIn(alias_key, subscriber.alias_maps)
        self.assertEqual(
            subscriber.alias_maps[alias_key][7],
            {"name": "pump_state", "datatype": 1, "props": {"unit": "kW"}},
        )

        alias_metric = sparkplug.Payload.Metric()
        alias_metric.alias = 7

        resolved = subscriber._resolve_name(
            subscriber.client, "Secil", "EdgeNode", "DeviceA", alias_metric
        )
        self.assertEqual(resolved, "pump_state")

    @pytest.mark.unit
    def test_resolve_name_prefers_device_alias_over_node_alias(self):
        subscriber = service.SparkplugSubscriber(self._make_settings())

        node_payload = sparkplug.Payload()
        node_metric = node_payload.metrics.add()
        node_metric.name = "node_temp"
        node_metric.alias = 5
        subscriber._ingest_birth("Secil", "EdgeNode", None, node_payload)

        device_payload = sparkplug.Payload()
        device_metric = device_payload.metrics.add()
        device_metric.name = "device_temp"
        device_metric.alias = 5
        subscriber._ingest_birth("Secil", "EdgeNode", "DeviceA", device_payload)

        metric = sparkplug.Payload.Metric()
        metric.alias = 5

        resolved = subscriber._resolve_name(
            subscriber.client, "Secil", "EdgeNode", "DeviceA", metric
        )
        self.assertEqual(resolved, "device_temp")

    @pytest.mark.unit
    def test_resolve_name_falls_back_to_node_alias_when_device_missing(self):
        subscriber = service.SparkplugSubscriber(self._make_settings())

        node_payload = sparkplug.Payload()
        node_metric = node_payload.metrics.add()
        node_metric.name = "node_pressure"
        node_metric.alias = 8
        subscriber._ingest_birth("Secil", "EdgeNode", None, node_payload)

        metric = sparkplug.Payload.Metric()
        metric.alias = 8

        resolved = subscriber._resolve_name(
            subscriber.client, "Secil", "EdgeNode", "DeviceB", metric
        )
        self.assertEqual(resolved, "node_pressure")

    @pytest.mark.unit
    def test_ingest_birth_preserves_nested_property_sets(self):
        subscriber = service.SparkplugSubscriber(self._make_settings())

        payload = sparkplug.Payload()
        metric = payload.metrics.add()
        metric.name = "pump_status"
        metric.alias = 3
        metric.datatype = 12

        props = metric.properties
        props.keys.extend(["unit", "limits", "modes"])

        unit_value = props.values.add()
        unit_value.string_value = "kW"

        limits_value = props.values.add()
        limits_set = limits_value.propertyset_value
        limits_set.keys.extend(["min", "max"])
        limits_set.values.add().int_value = 1
        limits_set.values.add().double_value = 9.5

        modes_value = props.values.add()
        modes_list = modes_value.propertysets_value
        auto_set = modes_list.propertyset.add()
        auto_set.keys.append("mode")
        auto_set.values.add().string_value = "AUTO"
        manual_set = modes_list.propertyset.add()
        manual_set.keys.append("mode")
        manual_set.values.add().string_value = "MANUAL"

        subscriber._ingest_birth("Secil", "EdgeNode", "DeviceA", payload)

        alias_key = ("Secil", "EdgeNode", "DeviceA")
        alias_entry = subscriber.alias_maps[alias_key][3]
        self.assertEqual(
            alias_entry,
            {
                "name": "pump_status",
                "datatype": 12,
                "props": {
                    "unit": "kW",
                    "limits": {"min": 1, "max": 9.5},
                    "modes": [{"mode": "AUTO"}, {"mode": "MANUAL"}],
                },
            },
        )

    @pytest.mark.unit
    def test_metric_value_handles_dataset_payload(self):
        dataset_metric = build_dataset_metric("combo_dataset", 2)

        parsed = service.SparkplugSubscriber._metric_value(dataset_metric)

        self.assertEqual(parsed["columns"], ["pressure", "temperature"])
        self.assertEqual(len(parsed["rows"]), 2)
        self.assertEqual(parsed["rows"][0][0], 10)
        self.assertAlmostEqual(parsed["rows"][0][1], 21.5)
        self.assertEqual(parsed["rows"][1][0], 12)
        self.assertAlmostEqual(parsed["rows"][1][1], 22.1, places=3)

    @pytest.mark.unit
    def test_resolve_name_requests_rebirth_with_throttle(self):
        subscriber = service.SparkplugSubscriber(
            self._make_settings(rebirth_throttle_seconds=60)
        )

        time_values = [1_000.0]

        def fake_time():
            return time_values[0]

        with patch.object(service.time, "time", side_effect=fake_time):
            metric = sparkplug.Payload.Metric()
            metric.alias = 9

            first = subscriber._resolve_name(
                subscriber.client, "Secil", "EdgeNode", "DeviceA", metric
            )
            self.assertEqual(first, "alias:9")
            self.assertEqual(
                subscriber.client.published,
                [("spBv1.0/Secil/EdgeNode/command/rebirth", b"")],
            )

            time_values[0] += 10
            second = subscriber._resolve_name(
                subscriber.client, "Secil", "EdgeNode", "DeviceA", metric
            )
            self.assertEqual(second, "alias:9")
            self.assertEqual(len(subscriber.client.published), 1)

            time_values[0] += 61
            subscriber._resolve_name(
                subscriber.client, "Secil", "EdgeNode", "DeviceA", metric
            )
            self.assertEqual(len(subscriber.client.published), 2)

    @pytest.mark.unit
    def test_on_message_decodes_payload_and_resolves_alias(self):
        subscriber = service.SparkplugSubscriber(self._make_settings())

        birth_payload = sparkplug.Payload()
        birth_payload.metrics.extend(
            [build_metric_with_property("flow_rate", 11, 2, "unit", "L/min")]
        )
        subscriber._ingest_birth("Secil", "EdgeNode", "DeviceA", birth_payload)

        captured = []

        def capture_jsonl(instance, topic, frame):
            captured.append((topic, frame))

        with patch.object(
            service.SparkplugSubscriber, "_write_jsonl", new=capture_jsonl
        ):
            message_payload = sparkplug.Payload()
            metric = message_payload.metrics.add()
            metric.alias = 11
            metric.int_value = 42
            metric.datatype = 1
            metric.timestamp = 123456789

            mqtt_message = types.SimpleNamespace(
                topic="spBv1.0/Secil/DBIRTH/EdgeNode/DeviceA",
                payload=message_payload.SerializeToString(),
            )

            subscriber.on_message(subscriber.client, None, mqtt_message)

        self.assertTrue(captured, "Expected _write_jsonl to be invoked")
        topic, frame = captured[0]
        self.assertEqual(topic, mqtt_message.topic)
        metric_frame = frame["metrics"][0]
        self.assertEqual(metric_frame["name"], "flow_rate")
        self.assertEqual(metric_frame["value"], 42)
        self.assertEqual(metric_frame["datatype"], 1)
        self.assertEqual(metric_frame["ts"], 123456789)
        self.assertEqual(metric_frame["props"], {})

    @pytest.mark.unit
    def test_on_message_populates_uns_paths(self):
        subscriber = service.SparkplugSubscriber(self._make_settings(write_jsonl=True))

        captured_frames = []

        def capture_frame(_topic, frame):
            captured_frames.append(frame)

        subscriber._write_jsonl = capture_frame  # type: ignore[assignment]

        payload = sparkplug.Payload()
        metric = payload.metrics.add()
        metric.name = "Area 1/Equipment-Alpha/Metric°"
        metric.alias = 5
        metric.datatype = 1

        message = types.SimpleNamespace(
            topic="spBv1.0/Secil/DBIRTH/Maceira-Ignition-Edge/Kiln-K1",
            payload=payload.SerializeToString(),
        )

        subscriber.on_message(subscriber.client, None, message)

        self.assertEqual(len(captured_frames), 1)
        frame = captured_frames[0]

        self.assertEqual(
            frame["device_uns_path"], "Secil/Maceira-Ignition-Edge/Kiln-K1"
        )

        metric_entry = frame["metrics"][0]
        self.assertEqual(
            metric_entry["uns_path"],
            "Secil/Maceira-Ignition-Edge/Kiln-K1/Area 1/Equipment-Alpha/Metric",
        )
        self.assertEqual(
            metric_entry["canary_id"],
            "Secil.Maceira-Ignition-Edge.Kiln-K1.Area 1.Equipment-Alpha.Metric",
        )

    @pytest.mark.unit
    def test_persist_frame_writes_device_metric_and_properties(self):
        repo = self.SpyRepository()
        subscriber = service.SparkplugSubscriber(
            self._make_settings(db_mode="local"), repository=repo
        )
        metrics = [
            {"name": "country", "value": "PT"},
            {"name": "business_unit", "value": "Cement"},
            {"name": "plant", "value": "PlantA"},
            {
                "name": "temperature",
                "value": 42.0,
                "datatype": "double",
                "uns_path": "SECIL.GROUP/EDGE-01/DEVICE-01/temperature",
                "props": {"engineering_unit": "C"},
            },
        ]
        frame = {
            "device_uns_path": "SECIL.GROUP/EDGE-01/DEVICE-01",
            "metrics": metrics,
        }

        subscriber._persist_frame("SECIL.GROUP", "EDGE-01", "DEVICE-01", frame)

        self.assertEqual(len(repo.device_payloads), 1)
        device_payload = repo.device_payloads[0]
        self.assertEqual(device_payload.group_id, "SECIL.GROUP")
        self.assertEqual(device_payload.business_unit, "Cement")
        self.assertEqual(device_payload.country, "PT")

        self.assertEqual(len(repo.metric_payloads), 1)
        metric_payload = repo.metric_payloads[0]
        self.assertEqual(metric_payload.datatype, "double")
        self.assertEqual(
            metric_payload.uns_path, "SECIL.GROUP/EDGE-01/DEVICE-01/temperature"
        )

        self.assertEqual(len(repo.property_payloads), 1)
        prop_payload = repo.property_payloads[0]
        self.assertEqual(prop_payload.type, "string")
        self.assertEqual(prop_payload.value, "C")

    @pytest.mark.unit
    def test_persist_frame_skips_when_repository_missing(self):
        subscriber = service.SparkplugSubscriber(self._make_settings(db_mode="mock"))
        frame = {"device_uns_path": "SECIL.GROUP/EDGE-01/DEVICE-01", "metrics": []}
        # Should not raise even without repository / DB
        subscriber._persist_frame("SECIL.GROUP", "EDGE-01", "DEVICE-01", frame)


@pytest.mark.unit
def test_service_runtime_skips_cdc_when_disabled(tmp_path, monkeypatch):
    settings = make_settings(tmp_path, cdc_enabled=False)
    monkeypatch.setattr(
        service.mqtt, "Client", lambda *args, **kwargs: StubClient(*args, **kwargs)
    )

    def _unexpected(*_args, **_kwargs):
        pytest.fail("CDC listener should not start")

    monkeypatch.setattr(service, "build_cdc_listener", _unexpected)
    runtime = service.ServiceRuntime(settings)
    runtime._start_cdc_listener()
    assert runtime._cdc_service is None


@pytest.mark.unit
def test_service_runtime_emits_diffs_and_stops(tmp_path, monkeypatch):
    settings = make_settings(
        tmp_path,
        cdc_enabled=True,
        db_mode="local",
        write_jsonl=True,
        jsonl_pattern=str(tmp_path / "messages_{topic}.jsonl"),
    )
    monkeypatch.setattr(
        service.mqtt, "Client", lambda *args, **kwargs: StubClient(*args, **kwargs)
    )

    class StubListener:
        def __init__(self):
            self.run_calls = 0
            self.stop_calls = 0
            self.started = threading.Event()

        def run_forever(self):
            self.run_calls += 1
            self.started.set()

        def stop(self):
            self.stop_calls += 1

    stub = StubListener()
    monkeypatch.setattr(service, "build_cdc_listener", lambda *_args, **_kwargs: stub)

    runtime = service.ServiceRuntime(settings)
    runtime._start_cdc_listener()
    assert runtime._cdc_service is stub
    assert stub.started.wait(1)

    runtime._handle_diff({"hello": "world"})
    jsonl_path = tmp_path / "messages_cdc_diff.jsonl"
    assert jsonl_path.exists()
    content = jsonl_path.read_text(encoding="utf-8").strip()
    assert content
    payload = json.loads(content)
    assert payload["hello"] == "world"

    runtime.stop()
    assert stub.stop_calls == 1


if __name__ == "__main__":
    unittest.main()
