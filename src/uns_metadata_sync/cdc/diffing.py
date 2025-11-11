"""Diff aggregation helpers used by the CDC debounce pipeline."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set


@dataclass(frozen=True)
class DiffEvent:
    """Represents a single change emitted from replication."""

    event_id: str
    uns_path: str
    version: int
    actor: str
    changes: Dict[str, object]
    timestamp: str


@dataclass
class AggregatedDiff:
    uns_path: str
    events: List[DiffEvent] = field(default_factory=list)
    merged_changes: Dict[str, tuple[int, object]] = field(default_factory=dict)

    def append(self, event: DiffEvent) -> None:
        self.events.append(event)
        for key, value in event.changes.items():
            current = self.merged_changes.get(key)
            if current is None or event.version >= current[0]:
                self.merged_changes[key] = (event.version, value)

    def to_snapshot(self) -> Dict[str, object]:
        ordered_events = sorted(self.events, key=lambda ev: ev.version)
        versions = [ev.version for ev in ordered_events]
        actors = [ev.actor for ev in ordered_events]
        metadata = {
            "latest_version": ordered_events[-1].version,
            "previous_version": (
                ordered_events[-2].version if len(ordered_events) > 1 else None
            ),
            "latest_actor": ordered_events[-1].actor,
            "actors": actors,
            "timestamps": [ev.timestamp for ev in ordered_events],
        }
        return {
            "uns_path": self.uns_path,
            "versions": versions,
            "metadata": metadata,
            "changes": {
                key: value for key, (version, value) in self.merged_changes.items()
            },
        }


class DiffAccumulator:
    """Merge metric/property diffs while tracking version metadata."""

    def __init__(self) -> None:
        self._entries: "OrderedDict[str, AggregatedDiff]" = OrderedDict()
        self._seen_event_ids: Set[str] = set()

    def apply(self, event: DiffEvent) -> bool:
        if event.event_id in self._seen_event_ids:
            return False
        self._seen_event_ids.add(event.event_id)
        entry = self._entries.get(event.uns_path)
        if entry is None:
            entry = AggregatedDiff(uns_path=event.uns_path)
            self._entries[event.uns_path] = entry
        entry.append(event)
        return True

    def extend(self, events: Iterable[DiffEvent]) -> int:
        applied = 0
        for event in events:
            if self.apply(event):
                applied += 1
        return applied

    def snapshot(self) -> List[Dict[str, object]]:
        return [entry.to_snapshot() for entry in self._entries.values()]

    def pop(self, uns_path: str) -> Optional[Dict[str, object]]:
        entry = self._entries.pop(uns_path, None)
        if entry is None:
            return None
        return entry.to_snapshot()

    def drain(self) -> List[Dict[str, object]]:
        snapshots: List[Dict[str, object]] = []
        for key in list(self._entries.keys()):
            snapshot = self.pop(key)
            if snapshot:
                snapshots.append(snapshot)
        return snapshots

    def seen_event_ids(self) -> Set[str]:
        return set(self._seen_event_ids)
