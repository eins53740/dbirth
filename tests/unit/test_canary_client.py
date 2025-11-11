from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pytest
import httpx

from uns_metadata_sync.canary.client import (
    CanaryClient,
    CanaryClientSettings,
    CanaryQueueFull,
)


@dataclass
class FakeClock:
    value: float = 0.0

    def advance(self, amount: float) -> None:
        self.value += amount

    def __call__(self) -> float:
        return self.value


def _make_diff(suffix: str) -> dict[str, object]:
    return {
        "uns_path": f"Secil/Portugal/Cement/Kiln/Metric{suffix}",
        "changes": {"engUnit": "C"},
    }


@pytest.mark.unit
def test_rate_limiter_enforces_rps_and_tracks_metrics() -> None:
    clock = FakeClock()
    sleeps: List[float] = []

    def fake_sleep(duration: float) -> None:
        sleeps.append(duration)
        clock.advance(duration)

    send_times: List[float] = []

    def sender(batch) -> None:
        send_times.append(clock.value)

    settings = CanaryClientSettings(
        base_url="https://example/api/v2",
        rate_limit_rps=2,
        burst_size=2,
        queue_capacity=10,
        max_batch_tags=1,
        retry_attempts=0,
        session_token="token",
    )
    client = CanaryClient(
        settings,
        request_sender=sender,
        clock=clock,
        sleep=fake_sleep,
        auto_start=False,
    )

    client.enqueue(_make_diff("A"))
    client.enqueue(_make_diff("B"))
    client.enqueue(_make_diff("C"))

    assert client.drain_once() is True
    assert client.drain_once() is True
    assert client.drain_once() is True

    assert len(send_times) == 3
    assert send_times[1] == pytest.approx(0.0, abs=1e-6)
    assert send_times[2] == pytest.approx(0.5, rel=1e-2)
    assert client._metrics.throttled_total >= 1
    assert client._metrics.queue_depth == 0
    client.stop()


@pytest.mark.unit
def test_queue_overflow_raises_and_counts_drop() -> None:
    settings = CanaryClientSettings(
        base_url="https://example/api/v2",
        queue_capacity=2,
        rate_limit_rps=10,
        burst_size=10,
        max_batch_tags=1,
        retry_attempts=0,
        session_token="token",
    )
    client = CanaryClient(settings, request_sender=lambda batch: None, auto_start=False)
    client.enqueue(_make_diff("1"))
    client.enqueue(_make_diff("2"))

    with pytest.raises(CanaryQueueFull):
        client.enqueue(_make_diff("3"))

    assert client._metrics.queue_dropped_total == 1
    client.stop()


@pytest.mark.unit
def test_retry_policy_applies_exponential_backoff_with_jitter() -> None:
    clock = FakeClock()
    sleeps: List[float] = []

    def fake_sleep(duration: float) -> None:
        sleeps.append(duration)
        clock.advance(duration)

    attempts = {"count": 0}

    def sender(batch) -> None:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("boom")

    settings = CanaryClientSettings(
        base_url="https://example/api/v2",
        rate_limit_rps=10,
        burst_size=10,
        queue_capacity=5,
        max_batch_tags=1,
        retry_attempts=2,
        retry_base_delay_seconds=0.2,
        retry_max_delay_seconds=0.8,
        circuit_consecutive_failures=99,
        jitter=lambda limit: limit,
        session_token="token",
    )
    client = CanaryClient(
        settings,
        request_sender=sender,
        clock=clock,
        sleep=fake_sleep,
        auto_start=False,
    )

    client.enqueue(_make_diff("R"))
    assert client.drain_once() is True

    assert attempts["count"] == 3
    assert client._metrics.retry_total == 2
    assert client._metrics.success_total == 1
    assert client._metrics.failure_total == 0
    assert client._metrics.circuit_state == "closed"
    assert len(sleeps) >= 2
    assert sleeps[0] == pytest.approx(0.2)
    assert sleeps[1] == pytest.approx(0.4)
    client.stop()


@pytest.mark.unit
def test_circuit_breaker_transitions_and_dead_letter_invoked() -> None:
    clock = FakeClock()
    sleeps: List[float] = []

    def fake_sleep(duration: float) -> None:
        sleeps.append(duration)
        clock.advance(duration)

    failures = {"count": 0}

    def sender(batch) -> None:
        if failures["count"] < 2:
            failures["count"] += 1
            raise RuntimeError("boom")

    dead_letters: List[tuple[str, str]] = []

    def dead_letter_handler(diff, error: Exception) -> None:
        dead_letters.append((diff.uns_path, str(error)))

    settings = CanaryClientSettings(
        base_url="https://example/api/v2",
        rate_limit_rps=10,
        burst_size=10,
        queue_capacity=5,
        max_batch_tags=1,
        retry_attempts=0,
        circuit_consecutive_failures=2,
        circuit_reset_seconds=5,
        session_token="token",
    )
    client = CanaryClient(
        settings,
        request_sender=sender,
        dead_letter_handler=dead_letter_handler,
        clock=clock,
        sleep=fake_sleep,
        auto_start=False,
    )

    client.enqueue(_make_diff("1"))
    client.drain_once()
    assert len(dead_letters) == 1
    assert client._metrics.circuit_state == "closed"

    client.enqueue(_make_diff("2"))
    client.drain_once()
    assert len(dead_letters) == 2
    assert client._metrics.circuit_state == "open"

    client.enqueue(_make_diff("3"))
    client.drain_once()
    assert client._metrics.circuit_state == "closed"
    assert len(dead_letters) == 2
    assert any(abs(sleep - 5.0) <= 0.05 for sleep in sleeps)
    assert client._metrics.circuit_open_total >= 1
    client.stop()


class StubSessionManager:
    def __init__(self) -> None:
        self.tokens = ["token-1", "token-2"]
        self.invalidated = 0
        self.get_calls = 0
        self.mark_calls = 0

    def get_token(self) -> str:
        value = self.tokens[min(self.invalidated, len(self.tokens) - 1)]
        self.get_calls += 1
        return value

    def invalidate(self) -> None:
        self.invalidated += 1

    def mark_activity(self) -> None:
        self.mark_calls += 1


@pytest.mark.unit
def test_session_token_reacquired_after_bad_session_error() -> None:
    attempts = {"count": 0}
    tokens_seen: List[str] = []
    session_manager = StubSessionManager()

    settings = CanaryClientSettings(
        base_url="https://example/api/v1",
        max_batch_tags=1,
        retry_attempts=1,
        session_token="fallback",
    )

    def sender(batch) -> None:
        attempts["count"] += 1
        tokens_seen.append(client._get_session_token())
        if attempts["count"] == 1:
            request = httpx.Request("POST", "https://example/api/v1/storeData")
            response = httpx.Response(
                401, request=request, json={"error": "BadSessionToken"}
            )
            raise httpx.HTTPStatusError("bad token", request=request, response=response)

    client = CanaryClient(
        settings,
        session_manager=session_manager,
        request_sender=sender,
        auto_start=False,
    )

    client.enqueue(_make_diff("S"))
    assert client.drain_once() is True
    client.stop()

    assert attempts["count"] == 2
    assert session_manager.invalidated == 1
    assert session_manager.mark_calls == 1
    assert tokens_seen == ["token-1", "token-2"]
    assert client._metrics.retry_total == 1
    assert client._metrics.failure_total == 0
