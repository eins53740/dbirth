"""Checkpoint store implementations for CDC resume tokens."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from threading import Lock, RLock
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class InMemoryCheckpointStore:
    """Volatile checkpoint store keeping slot positions in-memory."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._positions: Dict[str, int] = {}

    def load(self, slot_name: str) -> Optional[int]:
        with self._lock:
            return self._positions.get(slot_name)

    def save(self, slot_name: str, lsn: int) -> None:
        with self._lock:
            current = self._positions.get(slot_name)
            if current is None or lsn > current:
                self._positions[slot_name] = lsn

    def reset(
        self,
        slot_name: str,
        *,
        expected_lsn: Optional[int] = None,
        new_lsn: Optional[int] = None,
        force: bool = False,
    ) -> None:
        with self._lock:
            current = self._positions.get(slot_name)
            if current is None and new_lsn is None:
                if not force and expected_lsn not in (None, current):
                    raise ValueError("resume token missing; supply force=True to reset")
                return
            if not force:
                if current is None:
                    if expected_lsn not in (None, current):
                        raise ValueError(
                            "resume token missing; supply force=True to reset"
                        )
                else:
                    if expected_lsn is None or expected_lsn != current:
                        raise ValueError("unexpected resume token value")
                    if new_lsn is not None and new_lsn > current:
                        raise ValueError(
                            "new resume token must not exceed current value"
                        )
            if new_lsn is None:
                self._positions.pop(slot_name, None)
            else:
                self._positions[slot_name] = new_lsn


class PersistentCheckpointStore:
    """Durable checkpoint store that persists slot positions to disk atomically."""

    def __init__(self, path: Path | str, *, fsync: bool = False) -> None:
        self._path = Path(path)
        self._fsync = fsync
        self._lock = RLock()
        self._positions: Dict[str, int] = {}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - only raised on permission issues
            logger.warning(
                "unable to create checkpoint directory %s: %s",
                self._path.parent,
                exc,
            )
        self._load_from_disk()

    def load(self, slot_name: str) -> Optional[int]:
        with self._lock:
            return self._positions.get(slot_name)

    def save(self, slot_name: str, lsn: int) -> None:
        with self._lock:
            current = self._positions.get(slot_name)
            if current is not None and lsn <= current:
                return
            self._positions[slot_name] = lsn
            self._write_locked()

    def reset(
        self,
        slot_name: str,
        *,
        expected_lsn: Optional[int] = None,
        new_lsn: Optional[int] = None,
        force: bool = False,
    ) -> None:
        with self._lock:
            current = self._positions.get(slot_name)
            if current is None and new_lsn is None:
                if not force and expected_lsn not in (None, current):
                    raise ValueError("resume token does not exist for slot")
                return
            if not force:
                if current is None:
                    if expected_lsn not in (None, current):
                        raise ValueError("resume token does not exist for slot")
                else:
                    if expected_lsn is None or expected_lsn != current:
                        raise ValueError("unexpected resume token value")
                    if new_lsn is not None and new_lsn > current:
                        raise ValueError(
                            "new resume token must not exceed current value"
                        )
            if new_lsn is None:
                if current is None:
                    return
                self._positions.pop(slot_name, None)
            else:
                self._positions[slot_name] = new_lsn
            self._write_locked()

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "failed to load checkpoint file %s: %s", self._path, exc, exc_info=False
            )
            return
        if not isinstance(data, dict):
            logger.warning(
                "checkpoint file %s has invalid format; ignoring", self._path
            )
            return
        filtered: Dict[str, int] = {}
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, int):
                filtered[key] = value
        with self._lock:
            self._positions = filtered

    def _write_locked(self) -> None:
        temp_fd: Optional[int] = None
        temp_path: Optional[str] = None
        try:
            temp_fd, temp_path = tempfile.mkstemp(
                prefix=f".{self._path.name}.", dir=str(self._path.parent)
            )
            with os.fdopen(temp_fd, "w", encoding="utf-8") as tmp:
                temp_fd = None  # ownership transferred to file object
                json.dump(self._positions, tmp, sort_keys=True)
                tmp.flush()
                if self._fsync:
                    os.fsync(tmp.fileno())
            os.replace(temp_path, self._path)
            temp_path = None
            if self._fsync:
                try:
                    dir_fd = os.open(self._path.parent, os.O_RDONLY)
                except OSError:  # pragma: no cover - platform dependent
                    dir_fd = None
                if dir_fd is not None:
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
        except OSError as exc:
            logger.error("failed to persist checkpoint file %s: %s", self._path, exc)
            raise
        finally:
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except OSError:
                    pass
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


__all__ = ["InMemoryCheckpointStore", "PersistentCheckpointStore"]
