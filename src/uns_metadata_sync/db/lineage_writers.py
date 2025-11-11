"""Helpers for persisting lineage and version history entries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol

from . import Connection, Json


class _CounterProtocol(Protocol):
    def inc(self, amount: int = 1) -> None: ...


@dataclass
class _NullCounter:
    def inc(self, amount: int = 1) -> None:  # pragma: no cover - trivial no-op
        return None


class LineageVersionWriter:
    """Append-only writers for metric lineage and version history tables."""

    def __init__(
        self,
        conn: Connection,
        *,
        lineage_counter: Optional[_CounterProtocol] = None,
    ) -> None:
        self.conn = conn
        self._lineage_counter = lineage_counter or _NullCounter()

    def apply(
        self,
        *,
        metric_id: int,
        new_uns_path: str,
        diff: Mapping[str, Any] | None,
        previous_uns_path: Optional[str] = None,
        changed_by: str = "system",
    ) -> None:
        """Persist version history and optional lineage entry for a metric."""

        diff_payload: Mapping[str, Any] = diff or {}
        lineage_inserted = False

        with self.conn.transaction():
            if diff_payload:
                self.conn.execute(
                    """
                    INSERT INTO uns_meta.metric_versions (
                        metric_id,
                        changed_by,
                        diff
                    ) VALUES (%s, %s, %s)
                    """,
                    (metric_id, changed_by, Json(diff_payload)),
                )

            if (
                previous_uns_path
                and previous_uns_path != new_uns_path
                and previous_uns_path.strip()
            ):
                cursor = self.conn.execute(
                    """
                    INSERT INTO uns_meta.metric_path_lineage (
                        metric_id,
                        old_uns_path,
                        new_uns_path
                    ) VALUES (%s, %s, %s)
                    ON CONFLICT (metric_id, old_uns_path, new_uns_path) DO NOTHING
                    RETURNING lineage_id
                    """,
                    (metric_id, previous_uns_path, new_uns_path),
                )
                lineage_inserted = cursor.fetchone() is not None

        if lineage_inserted:
            self._lineage_counter.inc()


__all__ = ["LineageVersionWriter"]
