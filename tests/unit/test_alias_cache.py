import unittest
import sys
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from uns_metadata_sync.alias_cache import (
    deserialize_alias_maps,
    load_alias_cache,
    save_alias_cache,
    serialize_alias_maps,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


class AliasCacheHelpersTests(unittest.TestCase):
    @pytest.mark.unit
    def test_serialize_deserialize_round_trip_preserves_alias_maps(self):
        alias_maps = {
            ("Secil", "EdgeNode", "DeviceA"): {
                7: {"name": "pump_state", "datatype": 1, "props": {"unit": "kW"}}
            },
            ("Secil", "EdgeNode", None): {
                5: {"name": "node_temp", "datatype": 2, "props": {}}
            },
        }

        serialised = serialize_alias_maps(alias_maps)
        restored = deserialize_alias_maps(serialised)

        self.assertEqual(restored, alias_maps)

    @pytest.mark.unit
    def test_load_alias_cache_missing_file_returns_empty_dict(self):
        with TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "missing.json"
            self.assertEqual(load_alias_cache(path), {})

    @pytest.mark.unit
    def test_save_alias_cache_persists_round_trip(self):
        alias_maps = {
            ("Secil", "EdgeNode", "DeviceB"): {
                11: {"name": "flow_rate", "datatype": 1, "props": {"unit": "L/min"}}
            }
        }

        with TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "alias_cache.json"
            save_alias_cache(path, alias_maps)

            self.assertTrue(path.exists(), "expected alias cache file to be written")

            loaded = load_alias_cache(path)
            self.assertEqual(loaded, alias_maps)

            payload = path.read_text(encoding="utf-8")
            self.assertTrue(
                payload.endswith("\n"), "expected newline terminator for JSON file"
            )


if __name__ == "__main__":
    unittest.main()
