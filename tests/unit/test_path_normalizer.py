import json
import pytest
import sys
import types
import unittest
from pathlib import Path
from uns_metadata_sync import path_normalizer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"

# Provide stubs for optional dependencies in case the module imports them.
if "paho" not in sys.modules:
    paho_module = types.ModuleType("paho")
    mqtt_module = types.ModuleType("paho.mqtt")
    mqtt_client_module = types.ModuleType("paho.mqtt.client")

    class _DummyClient:  # pragma: no cover - placeholder only
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

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

normalize_device_path = path_normalizer.normalize_device_path
normalize_metric_path = path_normalizer.normalize_metric_path
metric_path_to_canary_id = path_normalizer.metric_path_to_canary_id

FIXTURE_PATH = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json"
)


class PathNormalizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        cls.sample_metric_name = payload["metrics"][0]["name"]

    @pytest.mark.unit
    def test_normalize_device_path_from_topic_segments(self) -> None:
        device_path = normalize_device_path(
            group="Secil",
            edge_node="Maceira-Ignition-Edge",
            device="Kiln-K1",
        )

        self.assertEqual(device_path, "Secil/Maceira-Ignition-Edge/Kiln-K1")

    @pytest.mark.unit
    def test_normalize_metric_path_extends_device_path_with_metric_segments(
        self,
    ) -> None:
        metric_path = normalize_metric_path(
            group="Secil",
            edge_node="Maceira-Ignition-Edge",
            device="Kiln-K1",
            metric_name=self.sample_metric_name,
        )

        expected = "/".join(
            [
                "Secil",
                "Maceira-Ignition-Edge",
                "Kiln-K1",
                "Maceira",
                "400 - Clinker Production",
                "451 - Bypass",
                "Normalised",
                "Indications",
                "BYPVT603INT02",
                "Active",
            ]
        )
        self.assertEqual(metric_path, expected)

    @pytest.mark.unit
    def test_metric_path_to_canary_id_replaces_slashes_with_dots(self) -> None:
        metric_path = (
            "Secil/Maceira-Ignition-Edge/Kiln-K1/Normalised Segment/Metric Value"
        )

        canary_id = metric_path_to_canary_id(metric_path)

        self.assertEqual(
            canary_id,
            "Secil.Maceira-Ignition-Edge.Kiln-K1.Normalised Segment.Metric Value",
        )

    @pytest.mark.unit
    def test_metric_normalization_preserves_non_ascii_characters(self) -> None:
        metric_path = normalize_metric_path(
            group="Secil",
            edge_node="S\u00e3o Sebasti\u00e3o",
            device="Bomba-01",
            metric_name="Linha/Tens\u00e3o/\u00c2ngulo",
        )

        self.assertIn("S\u00e3o Sebasti\u00e3o", metric_path)
        self.assertIn("Tens\u00e3o", metric_path)
        self.assertIn("\u00c2ngulo", metric_path)


if __name__ == "__main__":
    unittest.main()
