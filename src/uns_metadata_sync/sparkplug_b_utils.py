"""Helpers for working with Sparkplug B compressed payloads."""

from __future__ import annotations

import gzip as _gzip
import zlib as _zlib
from typing import Optional

from . import sparkplug_b_pb2 as sparkplug

__all__ = [
    "decode_sparkplug_payload",
    "unwrap_if_compressed",
    "is_compressed_wrapper",
    "CompressionError",
]


class CompressionError(Exception):
    """Raised when a payload claims compression but cannot be decompressed."""


def _metric_algorithm_value(payload: "sparkplug.Payload") -> Optional[str]:
    for metric in payload.metrics:
        is_string = getattr(metric, "WhichOneof")("value") == "string_value"
        if (
            metric.name == "algorithm"
            and not getattr(metric, "is_null", False)
            and is_string
        ):
            return getattr(metric, "string_value", None)
    return None


def is_compressed_wrapper(payload: "sparkplug.Payload") -> bool:
    """Return `True` when `payload` wraps a compressed Sparkplug message."""
    if (
        getattr(payload, "uuid", "") == "SPBV1.0_COMPRESSED"
        and len(getattr(payload, "body", b"")) > 0
    ):
        return True
    algorithm = _metric_algorithm_value(payload)
    return (algorithm == "GZIP") and len(getattr(payload, "body", b"")) > 0


def unwrap_if_compressed(payload: "sparkplug.Payload") -> "sparkplug.Payload":
    """Inflate nested payloads that use Sparkplug compression wrappers."""
    if not is_compressed_wrapper(payload):
        return payload
    body = getattr(payload, "body", b"")
    if not body:
        raise CompressionError("Compressed payload had empty body")
    try:
        inner_bytes = _gzip.decompress(body)
    except OSError:
        inner_bytes = _zlib.decompress(body, wbits=16 + _zlib.MAX_WBITS)
    inner = sparkplug.Payload()
    inner.ParseFromString(inner_bytes)
    return inner


def decode_sparkplug_payload(blob: bytes) -> "sparkplug.Payload":
    """Parse a payload and transparently unwrap any compression wrappers."""
    outer = sparkplug.Payload()
    outer.ParseFromString(blob)
    return unwrap_if_compressed(outer)
