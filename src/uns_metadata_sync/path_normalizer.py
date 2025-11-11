"""UNS path normalisation helpers.

The normaliser applies a consistent set of rules so that topics, edge nodes,
Sparkplug devices, and metric names map deterministically to slash-separated
UNS paths. These functions deliberately avoid depending on the wider service
runtime so that they can be exercised in isolation by unit tests.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Sequence

from .canary_id import generate_canary_id

_MULTIPLE_UNDERSCORES = re.compile(r"_{2,}")
_MULTIPLE_DASHES = re.compile(r"-{2,}")


def _split_value(value: object) -> List[str]:
    r"""Split a raw value into path segments using forward slashes only.

    Sparkplug names commonly embed hierarchy using ``/`` (e.g.
    ``"Area/Equipment/Metric"``); these are expanded into individual path
    components. Backslashes and other delimiters are left for the normalisation
    pass to sanitise rather than being treated as separators.
    """

    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        segments: List[str] = []
        for entry in value:
            segments.extend(_split_value(entry))
        return segments
    text = str(value).strip()
    if not text:
        return []
    return [segment for segment in text.split("/") if segment]


def _normalise_segment(segment: str) -> str:
    """Produce a sanitised path segment while preserving Unicode letters."""

    normalised = unicodedata.normalize("NFC", segment).strip()
    if not normalised:
        return ""

    cleaned_chars = []
    last_was_space = False
    for char in normalised:
        if char.isspace():
            if not last_was_space:
                cleaned_chars.append(" ")
                last_was_space = True
            continue

        last_was_space = False

        if char.isalnum() or char in {".", "_", "-"}:
            cleaned_chars.append(char)
        else:
            cleaned_chars.append("_")

    cleaned = "".join(cleaned_chars)
    cleaned = _MULTIPLE_UNDERSCORES.sub("_", cleaned)
    cleaned = _MULTIPLE_DASHES.sub("-", cleaned)
    cleaned = cleaned.strip("_ -")
    return cleaned


def _normalised_segments(*values: object) -> List[str]:
    """Flatten values and normalise them into safe path segments."""

    segments: List[str] = []
    for value in values:
        segments.extend(_split_value(value))
    normalised: List[str] = []
    for segment in segments:
        cleaned = _normalise_segment(segment)
        if cleaned:
            normalised.append(cleaned)
    return normalised


def normalize_device_path(
    *,
    group: str,
    edge_node: str,
    device: str | None,
    extra_segments: Sequence[str] | None = None,
) -> str:
    """Compute the canonical UNS path for a device context.

    Parameters
    ----------
    group:
        Sparkplug Group ID (first topic segment after ``spBv1.0``).
    edge_node:
        Sparkplug Edge Node identifier.
    device:
        Sparkplug Device identifier. DBIRTH frames include the device portion
        whereas NBIRTH frames omit it; ``None`` is allowed in that case.
    extra_segments:
        Optional additional path components (already ordered) that should appear
        directly after the device identity. This supports future extension
        without changing the function signature.
    """

    if not group:
        raise ValueError("group is required for UNS device path")
    if not edge_node:
        raise ValueError("edge_node is required for UNS device path")

    segments = _normalised_segments(group, edge_node, device, extra_segments or [])
    if not segments:
        raise ValueError("unable to derive any segments for UNS device path")
    return "/".join(segments)


def normalize_metric_path(
    *,
    group: str,
    edge_node: str,
    device: str | None,
    metric_name: str,
    extra_segments: Sequence[str] | None = None,
) -> str:
    r"""Compute the canonical UNS path for a metric.

    The metric path prefixes the device path and then appends the metric name
    split on ``/`` (and ``\``) according to Sparkplug conventions.
    """

    if not metric_name:
        raise ValueError("metric_name is required for UNS metric path")

    device_segments = _normalised_segments(group, edge_node, device)
    if not device_segments:
        raise ValueError("unable to derive device portion for metric path")

    metric_segments = _normalised_segments(extra_segments or [], metric_name)
    if not metric_segments:
        raise ValueError("metric_name did not yield any path segments")

    return "/".join(device_segments + metric_segments)


def metric_path_to_canary_id(metric_path: str) -> str:
    """Translate a UNS metric path into the dot-separated Canary identifier.

    Delegates to `generate_canary_id`, inheriting its escaping behaviour, logging,
    and collision metrics.
    """

    if not isinstance(metric_path, str):
        raise TypeError("metric_path must be a string")

    trimmed = metric_path.strip()
    if not trimmed:
        raise ValueError("metric_path must not be empty")

    return generate_canary_id(trimmed)


__all__ = [
    "metric_path_to_canary_id",
    "normalize_device_path",
    "normalize_metric_path",
]
