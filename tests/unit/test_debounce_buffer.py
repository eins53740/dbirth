import logging

import pytest

from uns_metadata_sync.cdc.debounce import DebounceBuffer, DebounceMetrics


class ManualClock:
    def __init__(self, start: float = 0.0) -> None:
        self._current = start

    def advance(self, seconds: float) -> float:
        self._current += seconds
        return self._current

    def __call__(self) -> float:
        return self._current


@pytest.mark.unit
def test_debounce_collapses_events_within_window():
    metrics = DebounceMetrics()
    clock = ManualClock()
    buffer = DebounceBuffer(
        window_seconds=120, max_entries=10, clock=clock, metrics=metrics
    )

    buffer.add(
        "metric-1", {"displayHigh": 1800}, version=1, actor="ingest", timestamp=clock()
    )
    clock.advance(60)
    buffer.add(
        "metric-1",
        {"displayHigh": 1750, "displayLow": 10},
        version=2,
        actor="cdc-listener",
        timestamp=clock(),
    )
    clock.advance(130)

    payloads = buffer.flush_due(now=clock())

    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["metric"] == "metric-1"
    assert payload["diff"] == {"displayHigh": 1750, "displayLow": 10}
    assert payload["version"] == 2
    assert payload["actor"] == "cdc-listener"
    assert metrics.gauges["buffer_depth"] == 0
    assert metrics.counters["emitted"] == 1
    assert buffer.pending_keys() == []


@pytest.mark.unit
def test_buffer_cap_triggers_drops_and_logs(caplog):
    caplog.set_level(logging.WARNING)
    metrics = DebounceMetrics()
    clock = ManualClock()
    buffer = DebounceBuffer(
        window_seconds=300, max_entries=2, clock=clock, metrics=metrics
    )

    buffer.add("metric-1", {"a": 1}, timestamp=clock())
    clock.advance(1)
    buffer.add("metric-2", {"b": 2}, timestamp=clock())
    clock.advance(1)
    buffer.add("metric-3", {"c": 3}, timestamp=clock())

    assert "dropping metric metric-1" in caplog.text
    assert metrics.counters["dropped"] == 1
    assert metrics.gauges["buffer_depth"] == 2
    assert sorted(buffer.pending_keys()) == ["metric-2", "metric-3"]


@pytest.mark.unit
def test_memory_footprint_bounded_by_cap():
    metrics = DebounceMetrics()
    clock = ManualClock()
    buffer = DebounceBuffer(
        window_seconds=60, max_entries=5, clock=clock, metrics=metrics
    )

    for idx in range(20):
        key = f"metric-{idx}"
        buffer.add(key, {"value": idx}, timestamp=clock())
        clock.advance(1)

    assert len(buffer.pending_keys()) == 5
    assert metrics.gauges["buffer_depth"] == 5
    assert metrics.counters["dropped"] == 15
