import gzip
import pytest
import sys
import unittest
from pathlib import Path

from uns_metadata_sync import sparkplug_b_pb2 as sparkplug
from uns_metadata_sync.sparkplug_b_utils import (
    decode_sparkplug_payload,
    unwrap_if_compressed,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


class SparkplugPayloadDecodeTests(unittest.TestCase):
    def _build_inner_payload(self):
        payload = sparkplug.Payload()
        metric = payload.metrics.add()
        metric.name = "motor_speed"
        metric.alias = 1
        metric.int_value = 42
        metric.datatype = 1
        return payload

    @pytest.mark.unit
    def test_decode_payload_unwraps_uuid_compressed_wrapper(self):
        inner = self._build_inner_payload()
        wrapped = sparkplug.Payload()
        wrapped.uuid = "SPBV1.0_COMPRESSED"
        wrapped.body = gzip.compress(inner.SerializeToString())

        decoded = decode_sparkplug_payload(wrapped.SerializeToString())

        self.assertEqual(decoded.metrics[0].name, "motor_speed")
        self.assertEqual(decoded.metrics[0].int_value, 42)

    @pytest.mark.unit
    def test_decode_payload_respects_algorithm_metric_wrapper(self):
        inner = self._build_inner_payload()
        wrapped = sparkplug.Payload()
        algorithm_metric = wrapped.metrics.add()
        algorithm_metric.name = "algorithm"
        algorithm_metric.string_value = "GZIP"
        wrapped.body = gzip.compress(inner.SerializeToString())

        decoded = decode_sparkplug_payload(wrapped.SerializeToString())

        self.assertEqual(decoded.metrics[0].alias, 1)
        self.assertEqual(decoded.metrics[0].datatype, 1)

    @pytest.mark.unit
    def test_unwrap_if_compressed_returns_original_when_body_missing(self):
        wrapped = sparkplug.Payload()
        wrapped.uuid = "SPBV1.0_COMPRESSED"
        wrapped.body = b""

        result = unwrap_if_compressed(wrapped)

        self.assertIs(result, wrapped)


if __name__ == "__main__":
    unittest.main()
