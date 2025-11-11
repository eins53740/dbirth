import pytest
import sys
import unittest
from pathlib import Path
from uns_metadata_sync import canary_id, path_normalizer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


class MetricPathToCanaryIdTests(unittest.TestCase):
    @pytest.mark.unit
    def test_simple_path_matches_canary_helper(self) -> None:
        uns_path = "Group/Area/Metric"
        self.assertEqual(
            path_normalizer.metric_path_to_canary_id(uns_path),
            canary_id.generate_canary_id(uns_path),
        )

    @pytest.mark.unit
    def test_non_ascii_and_space_segments_are_preserved(self) -> None:
        uns_path = "Group/Sub Métric/Value µ"
        canary_from_normalizer = path_normalizer.metric_path_to_canary_id(uns_path)
        self.assertEqual(
            canary_from_normalizer,
            canary_id.generate_canary_id(uns_path),
        )
        self.assertIn("Sub Métric", canary_from_normalizer)
        self.assertNotIn("_x", canary_from_normalizer)

    @pytest.mark.unit
    def test_blank_metric_path_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            path_normalizer.metric_path_to_canary_id("    ")


if __name__ == "__main__":
    unittest.main()
