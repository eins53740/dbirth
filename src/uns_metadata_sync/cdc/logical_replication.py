"""Logical replication helpers for processing `pgoutput` messages.

These utilities intentionally keep the implementation lightweight so they can be
unit tested without a live PostgreSQL connection.  The real CDC consumer wires
in psycopg replication cursors while tests provide simple iterators.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Optional, Protocol, Sequence


class CheckpointStore(Protocol):
    """Persistence backend used to store and retrieve replication slot positions."""

    def load(self, slot_name: str) -> Optional[int]: ...

    def save(self, slot_name: str, lsn: int) -> None: ...

    def reset(
        self,
        slot_name: str,
        *,
        expected_lsn: Optional[int] = None,
        new_lsn: Optional[int] = None,
        force: bool = False,
    ) -> None: ...


class ChangeDecoder(Protocol):
    """Decoder translating raw `pgoutput` messages into structured change records."""

    def decode(
        self, message: "ReplicationStreamMessage"
    ) -> Sequence["ChangeRecord"]: ...


class ChangeHandler(Protocol):
    """Callback invoked for each decoded change."""

    def __call__(self, change: "ChangeRecord") -> None: ...


@dataclass(frozen=True)
class ChangeColumn:
    """Describes a logical replication column value."""

    name: str
    value: object
    type_oid: int
    flags: Dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class ChangeRecord:
    """Structured representation of an individual change event."""

    kind: str  # insert, update, delete
    relation: str
    columns: Sequence[ChangeColumn]
    old_columns: Sequence[ChangeColumn] | None = None
    lsn: int = 0
    commit_timestamp: float = 0.0


@dataclass(frozen=True)
class ReplicationStreamMessage:
    """Raw message yielded by a logical replication stream."""

    lsn: int
    data: bytes
    commit_timestamp: float


class BackoffExhausted(RuntimeError):
    """Raised when the backoff policy has no further retries available."""


class ExponentialBackoff:
    """Exponential backoff helper with optional full jitter."""

    def __init__(
        self,
        base_interval: float = 0.5,
        multiplier: float = 2.0,
        max_interval: float = 30.0,
        max_attempts: Optional[int] = None,
        jitter: bool = True,
        random_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        if base_interval <= 0:
            raise ValueError("base_interval must be positive")
        if multiplier < 1:
            raise ValueError("multiplier must be at least 1.0")
        if max_interval < base_interval:
            raise ValueError("max_interval must be >= base_interval")
        self.base_interval = base_interval
        self.multiplier = multiplier
        self.max_interval = max_interval
        self.max_attempts = max_attempts
        self.jitter = jitter
        self.random_fn = random_fn or random.random
        self._attempt = 0

    @property
    def attempts(self) -> int:
        return self._attempt

    def reset(self) -> None:
        self._attempt = 0

    def next_delay(self) -> float:
        if self.max_attempts is not None and self._attempt >= self.max_attempts:
            raise BackoffExhausted("retry attempts exhausted")
        raw = min(
            self.base_interval * (self.multiplier**self._attempt), self.max_interval
        )
        self._attempt += 1
        if not self.jitter:
            return raw
        jitter_value = self.random_fn()
        return jitter_value * raw


class LogicalReplicationClient:
    """Coordinates decoding of replication messages and checkpoint persistence."""

    def __init__(
        self,
        slot_name: str,
        stream_factory: Callable[[Optional[int]], Iterable[ReplicationStreamMessage]],
        decoder: ChangeDecoder,
        checkpoint_store: CheckpointStore,
        handler: Optional[ChangeHandler] = None,
        checkpoint_interval: int = 50,
        backoff: Optional[ExponentialBackoff] = None,
    ) -> None:
        self.slot_name = slot_name
        self._stream_factory = stream_factory
        self._decoder = decoder
        self._checkpoint_store = checkpoint_store
        self._handler = handler
        self._checkpoint_interval = max(1, checkpoint_interval)
        self._backoff = backoff or ExponentialBackoff()
        self._last_seen_lsn: Optional[int] = None
        self._last_persisted_lsn: Optional[int] = None
        self._last_error_delay: Optional[float] = None

    @property
    def last_error_delay(self) -> Optional[float]:
        return self._last_error_delay

    def process(self, max_messages: Optional[int] = None) -> int:
        """Process messages from the replication stream."""
        start_lsn = self._checkpoint_store.load(self.slot_name)
        processed = 0
        stream = self._stream_factory(start_lsn)
        try:
            for message in stream:
                decoded = self._decoder.decode(message)
                for change in decoded:
                    processed += 1
                    if self._handler:
                        self._handler(change)
                    if max_messages and processed >= max_messages:
                        self._last_seen_lsn = message.lsn
                        if (
                            self._last_persisted_lsn is None
                            or self._last_seen_lsn > self._last_persisted_lsn
                        ):
                            self._persist_checkpoint(message.lsn)
                        self._backoff.reset()
                        self._last_error_delay = None
                        return processed
                self._last_seen_lsn = message.lsn
                if processed % self._checkpoint_interval == 0:
                    self._persist_checkpoint(message.lsn)
            if self._last_seen_lsn is not None:
                self._persist_checkpoint(self._last_seen_lsn)
            self._backoff.reset()
            self._last_error_delay = None
            return processed
        except Exception as exc:  # noqa: BLE001 - surfaced to caller with delay hint
            self._last_error_delay = self._backoff.next_delay()
            raise exc

    def _persist_checkpoint(self, lsn: int) -> None:
        if self._last_persisted_lsn is None or lsn > self._last_persisted_lsn:
            self._checkpoint_store.save(self.slot_name, lsn)
            self._last_persisted_lsn = lsn

    def reset_checkpoint(
        self,
        *,
        expected_lsn: Optional[int],
        new_lsn: Optional[int] = None,
        force: bool = False,
    ) -> None:
        """Reset the stored checkpoint while keeping client state consistent."""
        self._checkpoint_store.reset(
            self.slot_name,
            expected_lsn=expected_lsn,
            new_lsn=new_lsn,
            force=force,
        )
        self._last_seen_lsn = new_lsn
        self._last_persisted_lsn = new_lsn
        self._backoff.reset()
        self._last_error_delay = None
