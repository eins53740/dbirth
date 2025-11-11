"""Helpers to construct Canary Write API payloads from internal diffs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Mapping, Optional, Sequence

from ..path_normalizer import metric_path_to_canary_id


class PayloadTooLargeError(ValueError):
    """Raised when the encoded Canary payload exceeds the configured limit."""


@dataclass(frozen=True)
class CanaryDiff:
    """Normalized representation of a metric diff destined for Canary."""

    uns_path: str
    properties: Dict[str, object] = field(default_factory=dict)
    metadata: Dict[str, object] = field(default_factory=dict)
    actor: Optional[str] = None
    version: Optional[int] = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "CanaryDiff":
        """Build a ``CanaryDiff`` from assorted diff payload shapes."""
        raw_path = payload.get("uns_path") or payload.get("metric")
        if not isinstance(raw_path, str):
            raise ValueError("diff payload must include 'uns_path' or 'metric'")

        uns_path = raw_path.strip()
        if not uns_path:
            raise ValueError("metric path must not be empty")

        raw_properties = payload.get("changes")
        if raw_properties is None:
            raw_properties = payload.get("diff")
        properties: Dict[str, object] = {}
        if isinstance(raw_properties, Mapping):
            for key, value in raw_properties.items():
                properties[str(key)] = value
        elif isinstance(raw_properties, Sequence):
            for entry in raw_properties:
                if isinstance(entry, Mapping) and "key" in entry:
                    properties[str(entry["key"])] = entry.get("value")

        raw_metadata = payload.get("metadata") or payload.get("extras")
        metadata: Dict[str, object] = {}
        if isinstance(raw_metadata, Mapping):
            metadata = dict(raw_metadata)

        actor: Optional[str] = None
        raw_actor = payload.get("actor")
        if isinstance(raw_actor, str) and raw_actor.strip():
            actor = raw_actor
        elif isinstance(metadata.get("latest_actor"), str):
            actor = metadata["latest_actor"]

        version: Optional[int] = None
        raw_version = payload.get("version")
        if isinstance(raw_version, int):
            version = raw_version
        elif isinstance(metadata.get("latest_version"), int):
            version = metadata["latest_version"]

        return cls(
            uns_path=uns_path,
            properties=properties,
            metadata=metadata,
            actor=actor,
            version=version,
        )


class CanaryPayloadMapper:
    """Translate UNS metric diffs into Canary Write API request payloads."""

    def __init__(
        self,
        *,
        quality_code: int = 192,
        max_payload_bytes: int = 1_000_000,
        timestamp_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if max_payload_bytes <= 0:
            raise ValueError("max_payload_bytes must be positive")

        self._quality_code = quality_code
        self._max_payload_bytes = max_payload_bytes
        self._timestamp_provider = timestamp_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def build_payload(
        self,
        *,
        session_token: str,
        diffs: Sequence[CanaryDiff],
    ) -> Dict[str, object]:
        """Return a JSON-serialisable dict suitable for ``/storeData``."""
        token = session_token.strip()
        if not token:
            raise ValueError("session_token must not be empty")
        if not diffs:
            raise ValueError("diffs must not be empty")

        timestamp = self._normalise_timestamp(self._timestamp_provider())
        properties: Dict[str, list[list[object]]] = {}

        for diff in diffs:
            entries = self._build_entries(diff.properties, timestamp)
            if not entries:
                continue
            canary_id = metric_path_to_canary_id(diff.uns_path)
            properties[canary_id] = entries

        if not properties:
            raise ValueError("no diff entries yielded payload content")

        payload = {"sessionToken": token, "properties": properties}
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )

        if len(encoded) > self._max_payload_bytes:
            metrics = ", ".join(sorted(properties.keys()))
            raise PayloadTooLargeError(
                f"canary payload size {len(encoded)} bytes exceeds "
                f"limit {self._max_payload_bytes} (metrics: {metrics})"
            )
        return payload

    def _build_entries(
        self,
        properties: Mapping[str, object],
        timestamp: str,
    ) -> list[list[object]]:
        entries: list[list[object]] = []
        for key, raw_value in properties.items():
            key_str = key.strip() if isinstance(key, str) else str(key)
            if not key_str:
                continue
            value = self._encode_value(raw_value)
            entries.append([key_str, timestamp, value, self._quality_code])
        return entries

    @staticmethod
    def _normalise_timestamp(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _encode_value(value: object) -> object:
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            return value
        try:
            return json.loads(json.dumps(value, ensure_ascii=False))
        except (TypeError, ValueError):
            return str(value)
