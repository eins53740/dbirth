"""Canary Write API client with rate limiting, retries, and circuit breaker."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, List, Mapping, Optional, Sequence

import httpx

from .payload import CanaryDiff, CanaryPayloadMapper, PayloadTooLargeError
from .session import SAFSessionManager

logger = logging.getLogger(__name__)


class CanaryQueueFull(RuntimeError):
    """Raised when the enqueue buffer is at capacity."""


class CircuitBreakerOpenError(RuntimeError):
    """Raised when the circuit breaker blocks request dispatch."""


class CanaryRequestError(RuntimeError):
    """Wraps terminal request failures surfaced to callers."""


@dataclass(frozen=True)
class CanaryClientSettings:
    """Settings that control the Canary client behaviour."""

    base_url: str
    endpoint_path: str = "/storeData"
    request_timeout_seconds: float = 10.0
    rate_limit_rps: int = 500
    burst_size: int = 500
    queue_capacity: int = 1000
    max_batch_tags: int = 100
    max_payload_bytes: int = 1_000_000
    retry_attempts: int = 6
    retry_base_delay_seconds: float = 0.2
    retry_max_delay_seconds: float = 6.4
    circuit_consecutive_failures: int = 20
    circuit_reset_seconds: float = 60.0
    jitter: Optional[Callable[[float], float]] = None
    session_token: Optional[str] = None

    def resolve_endpoint(self) -> str:
        """Return the absolute endpoint URL for ``storeData`` calls."""
        base = self.base_url.rstrip("/")
        path = self.endpoint_path.strip()
        if not path:
            return base
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"


@dataclass
class CanaryClientMetrics:
    """Minimal metrics collector used for in-process assertions."""

    throttled_total: int = 0
    queue_depth: int = 0
    queue_dropped_total: int = 0
    requests_total: int = 0
    success_total: int = 0
    retry_total: int = 0
    failure_total: int = 0
    circuit_open_total: int = 0
    circuit_state: str = "closed"
    dead_letter_total: int = 0

    def inc_throttled(self) -> None:
        self.throttled_total += 1

    def inc_queue_dropped(self) -> None:
        self.queue_dropped_total += 1

    def set_queue_depth(self, depth: int) -> None:
        self.queue_depth = max(0, depth)

    def inc_requests(self) -> None:
        self.requests_total += 1

    def inc_success(self, count: int) -> None:
        self.success_total += count

    def inc_retry(self) -> None:
        self.retry_total += 1

    def inc_failure(self) -> None:
        self.failure_total += 1

    def inc_circuit_open(self) -> None:
        self.circuit_open_total += 1

    def set_circuit_state(self, state: str) -> None:
        self.circuit_state = state

    def inc_dead_letters(self, amount: int = 1) -> None:
        if amount <= 0:
            return
        self.dead_letter_total += amount

    def snapshot(self) -> dict[str, int | str]:
        return {
            "throttled_total": self.throttled_total,
            "queue_depth": self.queue_depth,
            "queue_dropped_total": self.queue_dropped_total,
            "requests_total": self.requests_total,
            "success_total": self.success_total,
            "retry_total": self.retry_total,
            "failure_total": self.failure_total,
            "circuit_open_total": self.circuit_open_total,
            "circuit_state": self.circuit_state,
            "dead_letter_total": self.dead_letter_total,
        }


class TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(
        self,
        *,
        rate_per_second: float,
        capacity: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._rate = float(rate_per_second)
        self._capacity = float(capacity)
        self._clock = clock
        self._tokens = float(capacity)
        self._updated_at = clock()

    def consume(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def time_until_ready(self, tokens: float = 1.0) -> float:
        self._refill()
        if self._tokens >= tokens:
            return 0.0
        deficit = tokens - self._tokens
        return deficit / self._rate

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._updated_at
        if elapsed <= 0:
            return
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._updated_at = now


class RetryPolicy:
    """Exponential backoff with jitter helper."""

    def __init__(
        self,
        *,
        attempts: int,
        base_delay: float,
        max_delay: float,
        jitter: Optional[Callable[[float], float]] = None,
    ) -> None:
        if attempts < 0:
            raise ValueError("attempts must be >= 0")
        if base_delay <= 0 or max_delay <= 0:
            raise ValueError("delays must be positive")
        self._retries = attempts
        self._jitter_fn = jitter or (lambda limit: random.uniform(0, limit))
        self._limits: List[float] = []
        delay = base_delay
        for _ in range(max(self._retries, 0)):
            self._limits.append(min(delay, max_delay))
            delay = min(delay * 2, max_delay)

    @property
    def max_attempts(self) -> int:
        """Return the total attempts (first try + retries)."""
        return self._retries + 1

    @property
    def retries(self) -> int:
        return self._retries

    def next_delay(self, attempt: int) -> float:
        """Return the backoff delay (seconds) before ``attempt``."""
        if attempt <= 1:
            return 0.0
        index = min(attempt - 2, len(self._limits) - 1)
        if index < 0:
            return 0.0
        limit = self._limits[index]
        return max(0.0, self._jitter_fn(limit))

    def all_delays(self) -> List[float]:
        """Return the theoretical upper bounds for each retry attempt."""
        return list(self._limits)


class CircuitBreaker:
    """Tracks failure streaks and blocks dispatch while open."""

    def __init__(
        self,
        *,
        failure_threshold: int,
        reset_timeout: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if reset_timeout <= 0:
            raise ValueError("reset_timeout must be positive")
        self._clock = clock
        self._threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0

    @property
    def state(self) -> str:
        return self._state

    def allow(self) -> bool:
        if self._state == "open":
            if self.time_until_allow() > 0:
                return False
            self._state = "half_open"
            self._failures = 0
            return True
        return True

    def time_until_allow(self) -> float:
        if self._state != "open":
            return 0.0
        elapsed = self._clock() - self._opened_at
        remaining = self._reset_timeout - elapsed
        return max(0.0, remaining)

    def record_success(self) -> None:
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0

    def record_failure(self) -> None:
        self._failures += 1
        if self._state in {"half_open", "open"} or self._failures >= self._threshold:
            self._state = "open"
            self._opened_at = self._clock()


class CanaryClient:
    """Bounded queue client that posts metadata diffs to Canary."""

    def __init__(
        self,
        settings: CanaryClientSettings,
        *,
        mapper: Optional[CanaryPayloadMapper] = None,
        metrics: Optional[CanaryClientMetrics] = None,
        request_sender: Optional[Callable[[Sequence[CanaryDiff]], None]] = None,
        dead_letter_handler: Optional[Callable[[CanaryDiff, Exception], None]] = None,
        session_manager: Optional[SAFSessionManager] = None,
        backpressure_handler: Optional[Callable[[CanaryDiff], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Optional[Callable[[float], None]] = None,
        auto_start: bool = True,
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._metrics = metrics or CanaryClientMetrics()
        self._mapper = mapper or CanaryPayloadMapper(
            max_payload_bytes=settings.max_payload_bytes
        )
        self._session_manager = session_manager
        self._dead_letter_handler = dead_letter_handler
        self._backpressure_handler = backpressure_handler
        self._queue: Deque[CanaryDiff] = deque()
        self._queue_cond = threading.Condition()
        self._stop_event = threading.Event()
        self._sleep = sleep or self._stop_event.wait
        self._bucket = TokenBucket(
            rate_per_second=float(settings.rate_limit_rps),
            capacity=float(settings.burst_size),
            clock=clock,
        )
        self._retry_policy = RetryPolicy(
            attempts=settings.retry_attempts,
            base_delay=settings.retry_base_delay_seconds,
            max_delay=settings.retry_max_delay_seconds,
            jitter=settings.jitter,
        )
        self._circuit = CircuitBreaker(
            failure_threshold=settings.circuit_consecutive_failures,
            reset_timeout=settings.circuit_reset_seconds,
            clock=clock,
        )
        self._request_sender = request_sender
        self._http_client: Optional[httpx.Client] = None
        self._endpoint = settings.resolve_endpoint()
        self._worker: Optional[threading.Thread] = None

        if self._request_sender is None:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            self._http_client = httpx.Client(
                timeout=settings.request_timeout_seconds,
                headers=headers,
            )
            self._request_sender = self._http_send

        if auto_start:
            self.start()

    # ------------------------------------------------------------------ Lifecycle
    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run_loop,
            name="canary-writer",
            daemon=True,
        )
        self._worker.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        with self._queue_cond:
            self._queue_cond.notify_all()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=timeout)
        self._worker = None
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def drain_once(self) -> bool:
        """Process a single batch synchronously; useful for tests."""
        return self._process_next_batch(block=False)

    # ------------------------------------------------------------------ Queue
    def enqueue(self, payload: Mapping[str, object] | CanaryDiff) -> None:
        diff = (
            payload
            if isinstance(payload, CanaryDiff)
            else CanaryDiff.from_mapping(payload)
        )
        with self._queue_cond:
            if len(self._queue) >= self._settings.queue_capacity:
                self._metrics.inc_queue_dropped()
                if self._backpressure_handler:
                    try:
                        self._backpressure_handler(diff)
                    except Exception:  # noqa: BLE001 - logging only
                        logger.exception("backpressure handler raised an error")
                raise CanaryQueueFull(
                    f"canary queue at capacity ({self._settings.queue_capacity})"
                )
            self._queue.append(diff)
            self._metrics.set_queue_depth(len(self._queue))
            self._queue_cond.notify()

    # ------------------------------------------------------------------ Internal loop
    def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                if not self._process_next_batch(block=True):
                    continue
        except Exception:  # noqa: BLE001
            logger.exception("canary writer loop terminated unexpectedly")

    def _process_next_batch(self, *, block: bool) -> bool:
        batch = self._acquire_batch(block=block)
        if not batch:
            return False
        self._dispatch(batch)
        return True

    def _acquire_batch(self, *, block: bool) -> Optional[List[CanaryDiff]]:
        while not self._stop_event.is_set():
            with self._queue_cond:
                if not self._queue:
                    if not block:
                        return None
                    self._queue_cond.wait(timeout=0.1)
                    continue

            if not self._circuit.allow():
                self._metrics.inc_circuit_open()
                self._metrics.set_circuit_state(self._circuit.state)
                self._wait(self._circuit.time_until_allow())
                continue

            if not self._bucket.consume():
                self._metrics.inc_throttled()
                wait_time = self._bucket.time_until_ready()
                self._wait(wait_time if wait_time > 0 else 0.01)
                continue

            with self._queue_cond:
                if not self._queue:
                    continue
                batch: List[CanaryDiff] = []
                while self._queue and len(batch) < self._settings.max_batch_tags:
                    batch.append(self._queue.popleft())
                self._metrics.set_queue_depth(len(self._queue))
            return batch
        return None

    def _dispatch(self, batch: Sequence[CanaryDiff]) -> None:
        self._metrics.inc_requests()
        attempt = 1
        while True:
            try:
                assert self._request_sender is not None
                self._request_sender(batch)
            except Exception as exc:  # noqa: BLE001
                session_invalidated = self._handle_session_error(exc)
                retriable = self._is_retriable(exc) or session_invalidated
                if attempt >= self._retry_policy.max_attempts or not retriable:
                    self._metrics.inc_failure()
                    self._circuit.record_failure()
                    self._metrics.set_circuit_state(self._circuit.state)
                    self._emit_dead_letter(batch, exc)
                    logger.error("Canary request failed permanently: %s", exc)
                    return
                self._metrics.inc_retry()
                self._circuit.record_failure()
                self._metrics.set_circuit_state(self._circuit.state)
                delay = self._retry_policy.next_delay(attempt + 1)
                self._wait(delay)
                attempt += 1
                continue
            else:
                self._metrics.inc_success(len(batch))
                self._circuit.record_success()
                self._metrics.set_circuit_state(self._circuit.state)
                if self._session_manager:
                    self._session_manager.mark_activity()
                break

    def _http_send(self, batch: Sequence[CanaryDiff]) -> None:
        session_token = self._get_session_token()
        payload = self._mapper.build_payload(
            session_token=session_token,
            diffs=batch,
        )
        assert self._http_client is not None
        response = self._http_client.post(
            self._endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

    def _get_session_token(self) -> str:
        if self._session_manager:
            return self._session_manager.get_token()
        if self._settings.session_token:
            return self._settings.session_token
        raise CanaryRequestError(
            "Session token not configured; provide CANARY_API_TOKEN or enable SAF session manager"
        )

    def _handle_session_error(self, error: Exception) -> bool:
        if not self._session_manager:
            return False
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            if status in {401, 403}:
                logger.info(
                    "SAF session invalid (status %s); reacquiring token", status
                )
                self._session_manager.invalidate()
                return True
            message = ""
            try:
                data = error.response.json()
            except Exception:  # noqa: BLE001
                data = None
            if isinstance(data, dict):
                message = str(
                    data.get("message") or data.get("error") or data.get("reason") or ""
                )
            elif data is not None:
                message = str(data)
            else:
                message = error.response.text
            if "BadSessionToken" in message or "sessionToken" in message:
                logger.info("SAF session reported BadSessionToken; reacquiring")
                self._session_manager.invalidate()
                return True
        return False

    def _is_retriable(self, error: Exception) -> bool:
        if isinstance(error, PayloadTooLargeError):
            return False
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            return status >= 500 or status == 429
        if isinstance(error, httpx.RequestError):
            return True
        return True

    def _emit_dead_letter(self, batch: Sequence[CanaryDiff], error: Exception) -> None:
        self._metrics.inc_dead_letters(len(batch))
        if not self._dead_letter_handler:
            return
        for diff in batch:
            try:
                self._dead_letter_handler(diff, error)
            except Exception:  # noqa: BLE001 - best effort
                logger.exception("dead-letter handler raised an error")

    def _wait(self, duration: float) -> None:
        if duration <= 0:
            return
        self._sleep(duration)
