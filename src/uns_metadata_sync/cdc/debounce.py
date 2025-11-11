"""Debounce buffer utilities for CDC diff aggregation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DebounceMetrics:
    """Very small abstraction over counters/gauges used in tests."""

    def __init__(self) -> None:
        self.counters: Dict[str, int] = {}
        self.gauges: Dict[str, float] = {}

    def inc(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def set_gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value


@dataclass
class DebounceEntry:
    metric_key: str
    first_seen: float
    last_update: float
    payload: Dict[str, object] = field(default_factory=dict)
    version: Optional[int] = None
    actor: Optional[str] = None
    event_ids: set[str] = field(default_factory=set)
    extras: Dict[str, object] = field(default_factory=dict)

    def merge(
        self,
        diff: Dict[str, object],
        *,
        version: Optional[int] = None,
        actor: Optional[str] = None,
        event_id: Optional[str] = None,
        timestamp: Optional[float] = None,
        extras: Optional[Dict[str, object]] = None,
    ) -> None:
        for key, value in diff.items():
            self.payload[key] = value
        if version is not None:
            if self.version is None or version >= self.version:
                self.version = version
        if actor:
            self.actor = actor
        if event_id:
            self.event_ids.add(event_id)
        if timestamp is not None:
            self.last_update = timestamp
        if extras:
            self.extras.update(extras)


class DebounceBuffer:
    """Aggregates metric diffs within a configured time window."""

    def __init__(
        self,
        window_seconds: float,
        max_entries: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        metrics: Optional[DebounceMetrics] = None,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.window_seconds = window_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._metrics = metrics or DebounceMetrics()
        self._entries: Dict[str, DebounceEntry] = {}
        self._sequence: List[str] = []

    @property
    def metrics(self) -> DebounceMetrics:
        return self._metrics

    def add(
        self,
        metric_key: str,
        diff: Dict[str, object],
        *,
        version: Optional[int] = None,
        actor: Optional[str] = None,
        event_id: Optional[str] = None,
        timestamp: Optional[float] = None,
        extras: Optional[Dict[str, object]] = None,
    ) -> None:
        now = timestamp if timestamp is not None else self._clock()
        entry = self._entries.get(metric_key)
        if entry is None:
            entry = DebounceEntry(
                metric_key=metric_key,
                first_seen=now,
                last_update=now,
            )
            self._entries[metric_key] = entry
            self._sequence.append(metric_key)
        entry.merge(
            diff,
            version=version,
            actor=actor,
            event_id=event_id,
            timestamp=now,
            extras=extras,
        )
        self._enforce_cap()
        self._metrics.set_gauge("buffer_depth", len(self._entries))

    def flush_due(self, *, now: Optional[float] = None) -> List[Dict[str, object]]:
        current = now if now is not None else self._clock()
        ready_keys = [
            key
            for key, entry in self._entries.items()
            if current - entry.last_update >= self.window_seconds
        ]
        ready_keys.sort(key=self._sequence.index)
        payloads: List[Dict[str, object]] = []
        for key in ready_keys:
            entry = self._entries.pop(key)
            self._sequence.remove(key)
            payloads.append(
                {
                    "metric": key,
                    "diff": dict(entry.payload),
                    "version": entry.version,
                    "actor": entry.actor,
                    "first_seen": entry.first_seen,
                    "last_update": entry.last_update,
                    "event_ids": sorted(entry.event_ids),
                    "extras": dict(entry.extras),
                }
            )
        if ready_keys:
            self._metrics.set_gauge("buffer_depth", len(self._entries))
            self._metrics.inc("emitted", len(ready_keys))
        return payloads

    def pending_keys(self) -> List[str]:
        return list(self._sequence)

    def _enforce_cap(self) -> None:
        while len(self._entries) > self.max_entries:
            oldest_key = min(
                self._entries.values(),
                key=lambda entry: entry.last_update,
            ).metric_key
            dropped = self._entries.pop(oldest_key)
            self._sequence.remove(oldest_key)
            self._metrics.inc("dropped")
            logger.warning(
                "debounce buffer full - dropping metric %s with %d pending keys",
                oldest_key,
                len(dropped.payload),
            )
