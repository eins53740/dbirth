from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Sequence, Tuple

import pytest

from uns_metadata_sync.canary import (
    CanaryClient,
    CanaryClientSettings,
    CanaryDiff,
    CanaryQueueFull,
)
from uns_metadata_sync.cdc.debounce import DebounceBuffer

pytestmark = pytest.mark.integration


class ManualClock:
    def __init__(self, start: float = 0.0) -> None:
        self._value = start

    def advance(self, seconds: float) -> float:
        self._value += seconds
        return self._value

    def __call__(self) -> float:
        return self._value


@dataclass
class FakeCanaryEndpoint:
    clock: ManualClock
    latency: float = 0.0
    fail_on_calls: Iterable[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._failures = set(self.fail_on_calls)
        self.calls: List[dict[str, object]] = []
        self.successful: List[dict[str, object]] = []
        self._call_index = 0

    def __call__(self, batch: Sequence[object]) -> None:
        start = self.clock()
        paths = tuple(getattr(diff, "uns_path", "<unknown>") for diff in batch)
        record = {"start": start, "paths": paths}
        self.calls.append(record)
        call_index = self._call_index
        self._call_index += 1

        if call_index in self._failures:
            if self.latency:
                self.clock.advance(self.latency)
            self._failures.remove(call_index)
            raise RuntimeError("forced failure")

        if self.latency:
            self.clock.advance(self.latency)
        self.successful.append(record)


def _build_debounced_payloads(
    clock: ManualClock, count: int
) -> List[dict[str, object]]:
    buffer = DebounceBuffer(window_seconds=0.1, max_entries=16, clock=clock)
    for idx in range(count):
        metric = f"Secil/Portugal/Cement/Kiln/Metric{idx}"
        buffer.add(
            metric,
            {"engUnit": "\u00b0C", "displayHigh": 150 + idx},
            actor="cdc-harness",
            version=idx + 1,
            event_id=f"cdc-{idx}",
            timestamp=clock(),
        )
        clock.advance(0.01)
    clock.advance(0.2)
    payloads = buffer.flush_due(now=clock())
    assert len(payloads) == count
    return payloads


def _unique_request_starts(records: Sequence[dict[str, object]]) -> List[float]:
    starts: List[float] = []
    last_paths: Tuple[str, ...] | None = None
    for entry in records:
        paths = entry["paths"]
        if paths != last_paths:
            starts.append(entry["start"])
            last_paths = paths  # type: ignore[assignment]
    return starts


def test_cdc_diff_flow_feeds_rate_limited_canary_client() -> None:
    clock = ManualClock()
    sleeps: List[float] = []

    def fake_sleep(duration: float) -> None:
        sleeps.append(duration)
        clock.advance(duration)

    backpressure_paths: List[str] = []
    dead_letters: List[Tuple[str, str]] = []

    def handle_backpressure(diff: CanaryDiff) -> None:
        backpressure_paths.append(diff.uns_path)

    def handle_dead_letter(diff: CanaryDiff, error: Exception) -> None:
        dead_letters.append((diff.uns_path, str(error)))

    endpoint = FakeCanaryEndpoint(clock, latency=0.01, fail_on_calls=[0])
    settings = CanaryClientSettings(
        base_url="https://canary.example",
        rate_limit_rps=4,
        burst_size=1,
        queue_capacity=3,
        max_batch_tags=2,
        retry_attempts=2,
        retry_base_delay_seconds=0.2,
        retry_max_delay_seconds=0.8,
        circuit_consecutive_failures=5,
        circuit_reset_seconds=5.0,
        jitter=lambda limit: limit,
        session_token="token",
    )
    client = CanaryClient(
        settings,
        request_sender=endpoint,
        clock=clock,
        sleep=fake_sleep,
        backpressure_handler=handle_backpressure,
        dead_letter_handler=handle_dead_letter,
        auto_start=False,
    )

    payloads = _build_debounced_payloads(clock, count=5)

    for payload in payloads:
        try:
            client.enqueue(payload)
        except CanaryQueueFull:
            assert backpressure_paths
            assert payload["metric"] == backpressure_paths[-1]
            assert client.drain_once() is True
            client.enqueue(payload)

    for _ in range(10):
        if not client.drain_once():
            break

    client.stop()

    assert client._metrics.requests_total >= 3
    assert not dead_letters
    assert len(backpressure_paths) == 1
    assert client._metrics.queue_dropped_total == 1
    assert client._metrics.success_total == len(payloads)
    assert client._metrics.retry_total == 1
    assert client._metrics.throttled_total >= 1

    request_starts = _unique_request_starts(endpoint.calls)
    assert len(request_starts) >= 3
    diffs = [b - a for a, b in zip(request_starts, request_starts[1:])]
    assert all(delta >= 0.25 - 1e-6 for delta in diffs)

    total_duration = request_starts[-1] - request_starts[0]
    observed_rate = (
        (len(request_starts) - 1) / total_duration if total_duration else 0.0
    )
    assert observed_rate <= 4.0 + 1e-6
