import json
from pathlib import Path

import pytest

from uns_metadata_sync.cdc.diffing import DiffAccumulator, DiffEvent

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def make_event(
    event_id: str,
    uns_path: str,
    version: int,
    actor: str,
    changes: dict[str, object],
    timestamp: str,
) -> DiffEvent:
    return DiffEvent(
        event_id=event_id,
        uns_path=uns_path,
        version=version,
        actor=actor,
        changes=changes,
        timestamp=timestamp,
    )


@pytest.mark.unit
def test_diff_accumulator_matches_golden_snapshot():
    accumulator = DiffAccumulator()
    events = [
        make_event(
            "evt-1",
            "Secil/Portugal/Cement/Maceira/Kiln/T1",
            5,
            "cdc-listener",
            {"displayHigh": 1800},
            "2025-09-01T12:00:00Z",
        ),
        make_event(
            "evt-2",
            "Secil/Portugal/Cement/Maceira/Kiln/T2",
            1,
            "cdc-listener",
            {"description": "Kiln feed rate"},
            "2025-09-01T12:01:00Z",
        ),
        make_event(
            "evt-3",
            "Secil/Portugal/Cement/Maceira/Kiln/T1",
            6,
            "cdc-writer",
            {"displayLow": 30, "engUnit": "C"},
            "2025-09-01T12:05:00Z",
        ),
    ]
    accumulator.extend(events)
    snapshot = accumulator.snapshot()
    golden = json.loads((FIXTURES / "golden_cdc_diff_snapshot.json").read_text())
    assert snapshot == golden


@pytest.mark.unit
def test_version_ordering_preserved_for_out_of_order_events():
    accumulator = DiffAccumulator()
    accumulator.apply(
        make_event(
            "evt-high",
            "Secil/Portugal/Cement/Maceira/Kiln/T3",
            7,
            "svc-a",
            {"displayHigh": 2000},
            "2025-09-01T12:10:00Z",
        )
    )
    accumulator.apply(
        make_event(
            "evt-low",
            "Secil/Portugal/Cement/Maceira/Kiln/T3",
            6,
            "svc-b",
            {"displayHigh": 1950, "comment": "backfill"},
            "2025-09-01T12:08:00Z",
        )
    )

    snapshot = accumulator.snapshot()
    assert snapshot[0]["versions"] == [6, 7]
    metadata = snapshot[0]["metadata"]
    assert metadata["latest_version"] == 7
    assert metadata["previous_version"] == 6
    assert snapshot[0]["changes"]["displayHigh"] == 2000
    assert snapshot[0]["changes"]["comment"] == "backfill"


@pytest.mark.unit
def test_duplicate_events_are_idempotent():
    accumulator = DiffAccumulator()
    event = make_event(
        "evt-dup",
        "Secil/Portugal/Cement/Maceira/Kiln/T4",
        3,
        "svc-a",
        {"displayHigh": 1500},
        "2025-09-01T12:12:00Z",
    )
    applied_first = accumulator.apply(event)
    applied_second = accumulator.apply(event)
    assert applied_first is True
    assert applied_second is False
    snapshot_before = accumulator.snapshot()
    drained = accumulator.drain()
    assert snapshot_before == drained
    assert accumulator.seen_event_ids() == {"evt-dup"}
    assert accumulator.snapshot() == []


@pytest.mark.unit
def test_pop_returns_snapshot_and_clears_entry():
    accumulator = DiffAccumulator()
    accumulator.apply(
        make_event(
            "evt-pop-1",
            "Secil/Portugal/Cement/Maceira/Kiln/T5",
            10,
            "svc-a",
            {"displayHigh": 1200},
            "2025-09-01T12:20:00Z",
        )
    )
    accumulator.apply(
        make_event(
            "evt-pop-2",
            "Secil/Portugal/Cement/Maceira/Kiln/T6",
            2,
            "svc-b",
            {"displayHigh": 1000},
            "2025-09-01T12:21:00Z",
        )
    )

    snapshot = accumulator.pop("Secil/Portugal/Cement/Maceira/Kiln/T5")
    assert snapshot is not None
    assert snapshot["uns_path"].endswith("T5")
    assert "displayHigh" in snapshot["changes"]
    assert accumulator.snapshot()[0]["uns_path"].endswith("T6")
