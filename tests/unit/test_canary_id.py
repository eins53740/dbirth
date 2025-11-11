import pytest
import sys
import types
import unittest
from pathlib import Path
from uns_metadata_sync.canary_id import CanaryIdGenerator, generate_canary_id

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

if "dotenv" not in sys.modules:
    sys.modules["dotenv"] = types.SimpleNamespace(
        load_dotenv=lambda *args, **kwargs: None
    )


class CanaryIdGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.generator = CanaryIdGenerator()

    @pytest.mark.unit
    def test_generate_returns_dot_delimited_canary_id(self):
        result = self.generator.generate(
            "Secil/Portugal/Cement/Maceira/Kiln/K1/Temperature/PV"
        )

        self.assertEqual(
            result.tag,
            "Secil.Portugal.Cement.Maceira.Kiln.K1.Temperature.PV",
        )
        self.assertIsNone(result.checksum)

    @pytest.mark.unit
    def test_generate_preserves_unicode_and_spaces(self):
        result = self.generator.generate(
            "Secil/Portugal/Cement/Outão/Raw Mill/RM-1/ΣCurrent"
        )

        self.assertEqual(
            result.tag,
            "Secil.Portugal.Cement.Outão.Raw Mill.RM-1.ΣCurrent",
        )
        self.assertIsNone(result.checksum)
        self.assertEqual(self.generator.escapes_total, 0)

    @pytest.mark.unit
    def test_generate_escapes_disallowed_symbols(self):
        with self.assertLogs(
            "uns_metadata_sync.canary_id", level="INFO"
        ) as log_capture:
            result = self.generator.generate("Secil/Plant/Line/Metric%Value")

        self.assertEqual(
            result.tag,
            "Secil.Plant.Line.Metric_x0025Value",
        )
        self.assertIsNone(result.checksum)
        self.assertEqual(self.generator.escapes_total, 1)
        self.assertTrue(
            any("escaped" in entry for entry in log_capture.output),
            "Expected escape log when disallowed characters present",
        )

    @pytest.mark.unit
    def test_generate_detects_collisions(self):
        first = self.generator.generate("Secil/Plant/Line/Metric")
        second = self.generator.generate("Secil/Plant//Line/Metric")

        self.assertEqual(first.tag, second.tag)
        self.assertEqual(self.generator.collisions_total, 1)

    @pytest.mark.unit
    def test_generate_supports_optional_checksum(self):
        result = self.generator.generate(
            "Secil/Plant/Line/Metric",
            include_checksum=True,
        )

        self.assertEqual(result.tag, "Secil.Plant.Line.Metric")
        self.assertEqual(result.checksum, "b98e735c")

    @pytest.mark.unit
    def test_generate_canary_id_function_returns_string_value(self):
        canary_id = generate_canary_id(
            "Secil/Portugal/Cement/Maceira/Kiln/K1/Temperature/PV"
        )

        self.assertEqual(
            canary_id,
            "Secil.Portugal.Cement.Maceira.Kiln.K1.Temperature.PV",
        )

    @pytest.mark.unit
    def test_generate_rejects_blank_input(self):
        with self.assertRaises(ValueError):
            self.generator.generate("   ")


if __name__ == "__main__":
    unittest.main()
