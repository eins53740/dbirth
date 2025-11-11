"""MQTT runtime for synchronising UNS/Sparkplug metadata."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import paho.mqtt.client as mqtt

from .alias_cache import AliasKey, AliasMap, load_alias_cache, save_alias_cache
from .config import Settings, load_settings
from .db import connect_from_settings
from .db.repository import (
    DevicePayload,
    MetadataRepository,
    MetricPayload,
    MetricPropertyPayload,
    RepositoryError,
)
from .path_normalizer import (
    metric_path_to_canary_id,
    normalize_device_path,
    normalize_metric_path,
)
from .sparkplug_b_utils import decode_sparkplug_payload
from . import sparkplug_b_pb2 as sparkplug
from .cdc import CDCListenerService, build_cdc_listener
from .canary import (
    CanaryClient,
    CanaryClientSettings,
    CanaryDiff,
    CanaryQueueFull,
    SAFSessionManager,
)


logger = logging.getLogger(__name__)


@dataclass
class SparkplugSubscriber:
    """Encapsulates MQTT lifecycle and Sparkplug alias resolution."""

    settings: Settings
    alias_maps: Dict[AliasKey, AliasMap] = field(default_factory=dict)
    repository: Optional[MetadataRepository] = None
    _last_rebirth_request: Dict[AliasKey, float] = field(default_factory=dict)
    _db_connection: Optional[object] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.alias_maps = load_alias_cache(self.settings.alias_cache_path)
        self.client = self._build_client()
        self._db_connection = None
        if self.repository is None and self.settings.db_mode == "local":
            self._initialise_repository()

    def _initialise_repository(self) -> None:
        try:
            conn = connect_from_settings(self.settings)
        except Exception as exc:
            print(f"[db] connection failed: {exc}")
            return
        self._db_connection = conn
        self.repository = MetadataRepository(conn)

    def _build_client(self) -> mqtt.Client:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.settings.client_id,
            protocol=mqtt.MQTTv311,
        )
        if self.settings.username or self.settings.password:
            client.username_pw_set(self.settings.username, self.settings.password)
        client.tls_set_context()
        client.tls_insecure_set(self.settings.tls_insecure)
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_message = self.on_message
        return client

    def connect(self) -> None:
        """Establish the MQTT connection."""
        if not self.settings.broker:
            raise RuntimeError(
                "MQTT broker host is not configured. Set MQTT_HOST or update the settings."
            )
        self.client.connect(self.settings.broker, self.settings.port, keepalive=60)

    def run(self) -> None:
        """Start the MQTT network loop and persist the alias cache on shutdown."""
        try:
            self.client.loop_forever()
        finally:
            save_alias_cache(self.settings.alias_cache_path, self.alias_maps)
            if self._db_connection is not None:
                try:
                    self._db_connection.close()
                finally:
                    self._db_connection = None

    # MQTT callbacks -----------------------------------------------------
    def on_connect(
        self, client: mqtt.Client, userdata, flags, reason_code, properties=None
    ) -> None:
        """Subscribe to the configured Sparkplug topics once connected."""
        rc = getattr(reason_code, "value", reason_code)
        if rc == 0:
            subscriptions = [
                (self.settings.topic_all, 0),
                (self.settings.topic_nbirth_all, 0),
                (self.settings.topic_dbirth_all, 0),
            ]
            print(
                "connected - subscribing to:",
                ", ".join(topic for topic, _ in subscriptions),
            )
            client.subscribe(subscriptions)
        else:
            print("connect failed - rc:", rc, "(", reason_code, ")")

    def on_disconnect(
        self,
        client: mqtt.Client,
        userdata,
        disconnect_flags,
        reason_code,
        properties=None,
    ) -> None:
        """Log disconnect events for easier troubleshooting."""
        rc = getattr(reason_code, "value", reason_code)
        reason_string = (
            getattr(properties, "ReasonString", None) if properties else None
        )
        detail = f", reason={reason_string}" if reason_string else ""
        print(
            f"disconnected: rc={rc} ({reason_code}){detail}, flags={disconnect_flags}"
        )

    def on_message(self, client: mqtt.Client, userdata, msg) -> None:
        """Decode Sparkplug payloads and enrich metrics with alias metadata."""
        parts = self._topic_parts(msg.topic)
        if not parts:
            return
        group, msg_type, edge_node, device = parts

        try:
            payload = decode_sparkplug_payload(msg.payload)
        except Exception as exc:  # noqa: BLE001 - log and continue consuming
            print("decode error:", exc)
            return

        device_uns_path = None
        try:
            device_uns_path = normalize_device_path(
                group=group,
                edge_node=edge_node,
                device=device,
            )
        except ValueError as exc:
            print(f"uns path device error for topic {msg.topic}: {exc}")

        if msg_type == "NBIRTH":
            self._ingest_birth(group, edge_node, None, payload)
        elif msg_type == "DBIRTH":
            self._ingest_birth(group, edge_node, device, payload)

        metrics = []
        device_for_alias = device if msg_type.startswith("D") else None
        for metric in payload.metrics:
            metrics.append(
                {
                    "name": self._resolve_name(
                        client, group, edge_node, device_for_alias, metric
                    ),
                    "value": self._metric_value(metric),
                    "datatype": int(getattr(metric, "datatype", 0)),
                    "ts": (
                        int(getattr(metric, "timestamp", 0))
                        if hasattr(metric, "timestamp")
                        else None
                    ),
                    "props": (
                        self._props_to_dict(metric.properties)
                        if hasattr(metric, "properties")
                        else {}
                    ),
                }
            )

        for metric in metrics:
            metric_name = metric.get("name", "")
            try:
                metric_uns_path = normalize_metric_path(
                    group=group,
                    edge_node=edge_node,
                    device=device,
                    metric_name=metric_name,
                )
                metric["uns_path"] = metric_uns_path
                metric["canary_id"] = metric_path_to_canary_id(metric_uns_path)
            except ValueError as exc:
                print(
                    "uns path metric error for",  # noqa: T201 - debug log
                    metric_name,
                    "on topic",
                    msg.topic,
                    ":",
                    exc,
                )

        frame = {
            "topic": msg.topic,
            "device_uns_path": device_uns_path,
            "metrics": metrics,
        }
        self._persist_frame(group, edge_node, device, frame)
        self._write_jsonl(msg.topic, frame)

    # Helpers ------------------------------------------------------------
    @staticmethod
    def _topic_parts(topic: str) -> Optional[Tuple[str, str, str, Optional[str]]]:
        parts = topic.split("/")
        if len(parts) < 4 or parts[0].lower() != "spbv1.0":
            return None
        group = parts[1]
        msg_type = parts[2].upper()
        edge_node = parts[3]
        device = parts[4] if len(parts) > 4 else None
        return group, msg_type, edge_node, device

    @staticmethod
    def _metric_value(metric) -> object:
        value_kind = metric.WhichOneof("value")
        if value_kind == "dataset_value":
            dataset = getattr(metric, value_kind)
            rows = []
            for row in dataset.rows:
                row_elements = []
                for element in row.elements:
                    element_kind = element.WhichOneof("value")
                    row_elements.append(
                        getattr(element, element_kind) if element_kind else None
                    )
                rows.append(row_elements)
            return {"columns": list(dataset.columns), "rows": rows}
        return getattr(metric, value_kind) if value_kind else None

    def _props_to_dict(self, props_set) -> Dict[str, object]:
        result: Dict[str, object] = {}
        if not hasattr(props_set, "keys"):
            return result
        try:
            for key, value in zip(props_set.keys, props_set.values):
                kind = value.WhichOneof("value")
                if kind == "propertyset_value":
                    result[key] = self._props_to_dict(getattr(value, kind))
                elif kind == "propertysets_value":
                    result[key] = [
                        self._props_to_dict(item)
                        for item in getattr(value, kind).propertyset
                    ]
                else:
                    result[key] = getattr(value, kind) if kind else None
        except Exception as exc:  # noqa: BLE001 - noisy data should not break ingestion
            print(f"[props] failed to parse properties: {exc}")
        return result

    def _persist_frame(
        self,
        group: str,
        edge_node: str,
        device: Optional[str],
        frame: Dict[str, object],
    ) -> None:
        if self.repository is None or self.settings.db_mode != "local":
            return
        device_uns_path = frame.get("device_uns_path")
        metrics = frame.get("metrics") or []
        if not device or not device_uns_path:
            return

        try:
            country = self._extract_dimension(metrics, "country", default="").strip()
            if not country:
                raise ValueError("missing required 'country' dimension")
        except Exception as exc:
            print(f"[db] {exc}; skipping persistence for this frame")
            return

        try:
            business_unit = self._extract_dimension(
                metrics, "business_unit", default=""
            ).strip()
            if not business_unit:
                raise ValueError("missing required 'business_unit' dimension")
        except Exception as exc:
            print(f"[db] {exc}; skipping persistence for this frame")
            return

        try:
            plant = self._extract_dimension(metrics, "plant", default="").strip()
            if not plant:
                raise ValueError("missing required 'plant' dimension")
        except Exception as exc:
            print(f"[db] {exc}; skipping persistence for this frame")
            return

        device_payload = DevicePayload(
            group_id=group,
            country=country,
            business_unit=business_unit,
            plant=plant,
            edge=edge_node,
            device=device,
            uns_path=device_uns_path,
        )
        try:
            with self.repository.conn.transaction():
                device_result = self.repository.upsert_device(device_payload)
                device_record = device_result.record
                device_id = device_record.get("device_id")
                if not device_id:
                    return

                metric_payloads = []
                for metric in metrics:
                    metric_name = metric.get("name")
                    metric_uns_path = metric.get("uns_path")
                    if not metric_name or not metric_uns_path:
                        continue

                    try:
                        metric_datatype = self._metric_datatype(metric.get("datatype"))
                    except Exception as exc:
                        print(f"[db] {exc}; skipping metric {metric_name}")
                        continue

                    metric_payloads.append(
                        MetricPayload(
                            device_id=device_id,
                            name=str(metric_name),
                            uns_path=metric_uns_path,
                            datatype=metric_datatype,
                        )
                    )

                if not metric_payloads:
                    return

                metric_id_map = self.repository.upsert_metrics_bulk(metric_payloads)

                property_payloads = []
                for metric in metrics:
                    metric_name = metric.get("name")
                    metric_id = metric_id_map.get(metric_name)
                    if not metric_id:
                        continue

                    props = metric.get("props") or {}
                    for key, value in props.items():
                        prop_payload = self._build_property_payload(
                            metric_id, key, value
                        )
                        if prop_payload is None:
                            continue
                        property_payloads.append(prop_payload)

                if property_payloads:
                    self.repository.upsert_metric_properties_bulk(
                        property_payloads, manage_transaction=False
                    )

        except RepositoryError as exc:
            print(
                f"[db] persistence failed for frame on topic {frame.get('topic')}: {exc}"
            )

    @staticmethod
    def _metric_datatype(raw: object) -> str:
        """Return a valid SparkplugB datatype string or raise if missing/invalid.

        The service must not persist metrics with unknown datatypes to comply
        with Sparkplug B expectations. Callers should catch exceptions and skip
        the offending metric.
        """
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        raise ValueError("missing or invalid 'datatype' for metric")

    @staticmethod
    def _extract_dimension(
        metrics: List[Dict[str, object]], key: str, default: str
    ) -> str:
        target = key.lower()
        for metric in metrics:
            name = str(metric.get("name", "")).lower()
            if name == target:
                value = metric.get("value")
                if isinstance(value, str):
                    stripped = value.strip()
                    if stripped:
                        return stripped
                elif value is not None:
                    return str(value)
        return default

    @staticmethod
    def _build_property_payload(
        metric_id: int, key: str, value: object
    ) -> Optional[MetricPropertyPayload]:
        if value is None:
            return None
        if isinstance(value, bool):
            return MetricPropertyPayload(
                metric_id=metric_id, key=key, type="boolean", value=value
            )
        if isinstance(value, int) and not isinstance(value, bool):
            type_name = "int" if -2147483648 <= value <= 2147483647 else "long"
            return MetricPropertyPayload(
                metric_id=metric_id, key=key, type=type_name, value=value
            )
        if isinstance(value, float):
            return MetricPropertyPayload(
                metric_id=metric_id, key=key, type="double", value=value
            )
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            return MetricPropertyPayload(
                metric_id=metric_id, key=key, type="string", value=stripped
            )
        return None

    def _write_jsonl(self, topic: str, frame: Dict[str, object]) -> None:
        if not self.settings.write_jsonl:
            return
        topic_slug = topic.replace("/", "_")
        path = Path(self.settings.jsonl_pattern.format(topic=topic_slug))
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(frame, ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001 - best effort logging only
            print(f"[jsonl] write failed: {exc}")

    def _key(self, group: str, edge_node: str, device: Optional[str]) -> AliasKey:
        return group, edge_node, device

    def _ensure_map(
        self, group: str, edge_node: str, device: Optional[str]
    ) -> AliasMap:
        key = self._key(group, edge_node, device)
        if key not in self.alias_maps:
            self.alias_maps[key] = {}
        return self.alias_maps[key]

    def _may_request_rebirth(
        self, client: mqtt.Client, group: str, edge_node: str, device: Optional[str]
    ) -> None:
        if not self.settings.auto_request_rebirth:
            return
        now = time.time()
        throttle_key = self._key(group, edge_node, device)
        last_request = self._last_rebirth_request.get(throttle_key, 0)
        if now - last_request < self.settings.rebirth_throttle_seconds:
            return
        topic = f"spBv1.0/{group}/{edge_node}/command/rebirth"
        print(f"requesting rebirth for {group}/{edge_node}/{device or '*'}")
        client.publish(topic, payload=b"")
        self._last_rebirth_request[throttle_key] = now

    def _ingest_birth(
        self,
        group: str,
        edge_node: str,
        device: Optional[str],
        payload: sparkplug.Payload,
    ) -> None:
        alias_map = self._ensure_map(group, edge_node, device)
        for metric in payload.metrics:
            alias = int(getattr(metric, "alias", 0))
            name = getattr(metric, "name", "")
            if alias <= 0 or not name:
                continue
            alias_map[alias] = {
                "name": name,
                "datatype": int(getattr(metric, "datatype", 0)),
                "props": (
                    self._props_to_dict(getattr(metric, "properties", None))
                    if hasattr(metric, "properties")
                    else {}
                ),
            }

    def _resolve_name(
        self,
        client: mqtt.Client,
        group: str,
        edge_node: str,
        device: Optional[str],
        metric,
    ) -> str:
        name = getattr(metric, "name", "") or ""
        if name:
            return name
        alias = int(getattr(metric, "alias", 0))
        if not alias:
            return ""
        for lookup in (
            self._key(group, edge_node, device),
            self._key(group, edge_node, None),
        ):
            alias_map = self.alias_maps.get(lookup)
            if alias_map and alias in alias_map:
                return alias_map[alias]["name"]
        self._may_request_rebirth(client, group, edge_node, device)
        return f"alias:{alias}"


class ServiceRuntime:
    """Coordinates the MQTT subscriber and optional CDC listener."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.subscriber = SparkplugSubscriber(settings)
        self._cdc_service: Optional[CDCListenerService] = None
        self._cdc_thread: Optional[threading.Thread] = None
        self._canary_client: Optional[CanaryClient] = None
        self._session_manager: Optional[SAFSessionManager] = None

        if (
            self.settings.canary_enabled
            and self.settings.canary_base_url
            and self.settings.canary_api_token
        ):
            session_manager: Optional[SAFSessionManager] = None
            try:
                session_manager = SAFSessionManager(
                    base_url=self.settings.canary_base_url,
                    api_token=self.settings.canary_api_token,
                    client_id=self.settings.canary_client_id or self.settings.client_id,
                    historians=self.settings.canary_historians,
                    session_timeout_ms=self.settings.canary_session_timeout_ms,
                    keepalive_idle_seconds=self.settings.canary_keepalive_idle_seconds,
                    keepalive_jitter_seconds=self.settings.canary_keepalive_jitter_seconds,
                )
                self._session_manager = session_manager
                canary_settings = CanaryClientSettings(
                    base_url=self.settings.canary_base_url,
                    request_timeout_seconds=self.settings.canary_request_timeout_seconds,
                    rate_limit_rps=self.settings.canary_rate_limit_rps,
                    burst_size=self.settings.canary_rate_limit_rps,
                    queue_capacity=self.settings.canary_queue_capacity,
                    max_batch_tags=self.settings.canary_max_batch_tags,
                    max_payload_bytes=self.settings.canary_max_payload_bytes,
                    retry_attempts=self.settings.canary_retry_attempts,
                    retry_base_delay_seconds=self.settings.canary_retry_base_delay_seconds,
                    retry_max_delay_seconds=self.settings.canary_retry_max_delay_seconds,
                    circuit_consecutive_failures=self.settings.canary_circuit_consecutive_failures,
                    circuit_reset_seconds=self.settings.canary_circuit_reset_seconds,
                )
                self._canary_client = CanaryClient(
                    canary_settings,
                    session_manager=session_manager,
                    auto_start=False,
                    dead_letter_handler=self._handle_dead_letter,
                )
            except Exception:  # noqa: BLE001 - initialization is best-effort
                if session_manager is not None:
                    try:
                        session_manager.revoke()
                    finally:
                        session_manager.close()
                self._session_manager = None
                logger.exception("failed to initialise Canary client")
                self._canary_client = None

    def run(self) -> None:
        try:
            self.subscriber.connect()
        except Exception as exc:  # noqa: BLE001
            logger.exception("failed to connect to MQTT broker: %s", exc)
            return
        if self._canary_client:
            self._canary_client.start()
        self._start_cdc_listener()
        try:
            self.subscriber.run()
        except KeyboardInterrupt:
            logger.info("shutdown requested (KeyboardInterrupt)")
        finally:
            self.stop()

    def stop(self) -> None:
        if self._cdc_service is not None:
            self._cdc_service.stop()
        if self._cdc_thread and self._cdc_thread.is_alive():
            self._cdc_thread.join(timeout=5)
        if self._canary_client is not None:
            try:
                self._canary_client.stop()
            except Exception:  # noqa: BLE001 - best effort
                logger.exception("failed to stop Canary client cleanly")
        if self._session_manager is not None:
            try:
                self._session_manager.revoke()
            finally:
                self._session_manager.close()
                self._session_manager = None
        client = getattr(self.subscriber, "client", None)
        if client and hasattr(client, "disconnect"):
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001 - best effort
                pass

    def _start_cdc_listener(self) -> None:
        if not self.settings.cdc_enabled:
            logger.info("CDC listener disabled via configuration")
            return
        if self.settings.db_mode != "local":
            logger.info(
                "CDC listener requires DB_MODE=local; skipping (DB_MODE=%s)",
                self.settings.db_mode,
            )
            return
        try:
            self._cdc_service = build_cdc_listener(
                self.settings,
                diff_sink=self._handle_diff,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("unable to start CDC listener: %s", exc)
            self._cdc_service = None
            return

        self._cdc_thread = threading.Thread(
            target=self._run_cdc_loop,
            name="cdc-listener",
            daemon=True,
        )
        self._cdc_thread.start()
        logger.info("CDC listener started in background")

    def _run_cdc_loop(self) -> None:
        if self._cdc_service is None:
            return
        try:
            self._cdc_service.run_forever()
        except Exception:  # noqa: BLE001
            logger.exception("CDC listener encountered an unrecoverable error")

    def _handle_diff(self, payload: Dict[str, object]) -> None:
        if self.settings.write_jsonl:
            path = Path(self.settings.jsonl_pattern.format(topic="cdc_diff"))
            try:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            except Exception as exc:  # noqa: BLE001 - best effort logging
                logger.error("failed to write CDC diff JSONL: %s", exc)
        logger.info("CDC diff emitted: %s", json.dumps(payload, sort_keys=True))
        if self._canary_client is None:
            return
        try:
            self._canary_client.enqueue(payload)
        except CanaryQueueFull:
            metric_path = payload.get("uns_path") or payload.get("metric")
            logger.warning("Canary queue full - dropping diff for %s", metric_path)
        except Exception:  # noqa: BLE001
            logger.exception("failed to enqueue diff for Canary client")

    def _handle_dead_letter(self, diff: CanaryDiff, error: Exception) -> None:
        metric_path = getattr(diff, "uns_path", None)
        logger.error(
            "canary dead-lettered diff for %s: %s",
            metric_path or "<unknown>",
            error,
        )


def main() -> None:
    """Entrypoint used by both python -m and the console script hook."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        )
    settings = load_settings()
    runtime = ServiceRuntime(settings)
    runtime.run()
