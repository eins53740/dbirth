from __future__ import annotations

from datetime import datetime, timezone

import pytest

from uns_metadata_sync.canary.payload import (
    CanaryDiff,
    CanaryPayloadMapper,
    PayloadTooLargeError,
)


def _fixed_timestamp() -> datetime:
    return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_canary_payload_mapper_maps_properties() -> None:
    mapper = CanaryPayloadMapper(
        max_payload_bytes=4096,
        timestamp_provider=_fixed_timestamp,
    )
    diff = CanaryDiff(
        uns_path="Secil/Portugal/Cement/Kiln/Temperature",
        properties={"engUnit": "\u00b0C", "displayHigh": 1800},
    )

    payload = mapper.build_payload(session_token="token-123", diffs=[diff])

    assert payload["sessionToken"] == "token-123"
    tag_id = "Secil.Portugal.Cement.Kiln.Temperature"
    assert tag_id in payload["properties"]
    entries = payload["properties"][tag_id]
    assert len(entries) == 2
    first = entries[0]
    assert first[0] == "engUnit"
    assert first[1] == "2025-01-01T12:00:00.000000Z"
    assert first[2] == "\u00b0C"
    assert first[3] == 192
    second = entries[1]
    assert second[0] == "displayHigh"
    assert second[1] == "2025-01-01T12:00:00.000000Z"
    assert second[2] == 1800
    assert second[3] == 192


@pytest.mark.unit
def test_canary_payload_mapper_handles_optional_nulls() -> None:
    mapper = CanaryPayloadMapper(
        max_payload_bytes=4096,
        timestamp_provider=_fixed_timestamp,
    )
    diff = CanaryDiff(
        uns_path="Secil/Portugal/Cement/Kiln/Pressure",
        properties={"description": None, "enabled": True},
    )

    payload = mapper.build_payload(session_token="token-abc", diffs=[diff])
    entries = payload["properties"]["Secil.Portugal.Cement.Kiln.Pressure"]
    values = {entry[0]: entry[2] for entry in entries}
    assert values["description"] == ""
    assert values["enabled"] == "true"


@pytest.mark.unit
def test_canary_payload_mapper_enforces_size_limit() -> None:
    mapper = CanaryPayloadMapper(
        max_payload_bytes=120,
        timestamp_provider=_fixed_timestamp,
    )
    bloated = CanaryDiff(
        uns_path="Secil/Portugal/Cement/Kiln/Excessive",
        properties={"notes": "x" * 200},
    )

    with pytest.raises(PayloadTooLargeError) as excinfo:
        mapper.build_payload(session_token="token", diffs=[bloated])

    message = str(excinfo.value)
    assert "Secil.Portugal.Cement.Kiln.Excessive" in message
    assert "exceeds" in message
