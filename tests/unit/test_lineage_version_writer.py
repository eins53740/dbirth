from __future__ import annotations
import pytest
from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence

from uns_metadata_sync.db import Json

from uns_metadata_sync.db.lineage_writers import LineageVersionWriter


class _FakeCursor:
    def __init__(self, rows: Sequence[dict[str, Any]] | None):
        self._rows: List[dict[str, Any]] = list(rows or [])
        self._index = 0

    def fetchone(self) -> dict[str, Any] | None:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row


class _FakeTransaction:
    def __init__(self, conn: "_FakeConnection"):
        self._conn = conn
        self._conn.transaction_calls += 1

    def __enter__(self) -> None:
        return None

    def __exit__(
        self, exc_type, exc, tb
    ) -> bool:  # pragma: no cover - behaviour not exercised
        return False


class _FakeConnection:
    def __init__(self, responses: Iterable[Sequence[dict[str, Any]] | None]):
        self._responses = iter(responses)
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.transaction_calls = 0

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def execute(self, query: str, params: Any) -> _FakeCursor:
        leading = query.strip().splitlines()[0]
        self.executed.append((leading, params))
        response = next(self._responses, None)
        if isinstance(response, Exception):
            raise response
        return _FakeCursor(response)


@dataclass
class _Counter:
    count: int = 0

    def inc(self, amount: int = 1) -> None:
        self.count += amount


@pytest.mark.unit
def test_apply_writes_version_and_lineage_entries() -> None:
    diff = {"updated": {"display_name": {"old": "Old", "new": "New"}}}

    conn = _FakeConnection(
        responses=[
            [{"version_id": 11}],
            [{"lineage_id": 7}],
        ]
    )
    counter = _Counter()

    writer = LineageVersionWriter(conn, lineage_counter=counter)

    writer.apply(
        metric_id=101,
        new_uns_path="Group/Edge/Device/Metric",
        diff=diff,
        previous_uns_path="Group/Edge/Device/Metric-Old",
        changed_by="planner",
    )

    assert conn.transaction_calls == 1
    assert len(conn.executed) == 2

    version_query, version_params = conn.executed[0]
    assert version_query.startswith("INSERT INTO uns_meta.metric_versions")
    assert version_params[0] == 101
    assert version_params[1] == "planner"
    assert isinstance(version_params[2], Json)
    assert version_params[2].obj == diff

    lineage_query, lineage_params = conn.executed[1]
    assert lineage_query.startswith("INSERT INTO uns_meta.metric_path_lineage")
    assert lineage_params == (
        101,
        "Group/Edge/Device/Metric-Old",
        "Group/Edge/Device/Metric",
    )

    assert counter.count == 1


@pytest.mark.unit
def test_apply_skips_lineage_when_paths_match() -> None:
    conn = _FakeConnection(
        responses=[
            [{"version_id": 12}],
        ]
    )
    counter = _Counter()
    writer = LineageVersionWriter(conn, lineage_counter=counter)

    writer.apply(
        metric_id=55,
        new_uns_path="A/B/C",
        diff={"added": {"unit": "C"}},
        previous_uns_path="A/B/C",
        changed_by="planner",
    )

    assert conn.transaction_calls == 1
    assert len(conn.executed) == 1
    query, _ = conn.executed[0]
    assert query.startswith("INSERT INTO uns_meta.metric_versions")
    assert counter.count == 0


@pytest.mark.unit
def test_apply_records_lineage_without_diff() -> None:
    conn = _FakeConnection(
        responses=[
            [{"lineage_id": 3}],
        ]
    )
    counter = _Counter()
    writer = LineageVersionWriter(conn, lineage_counter=counter)

    writer.apply(
        metric_id=77,
        new_uns_path="Group/Edge/Device/NewMetric",
        diff={},
        previous_uns_path="Group/Edge/Device/Metric",
        changed_by="planner",
    )

    assert conn.transaction_calls == 1
    assert len(conn.executed) == 1
    query, params = conn.executed[0]
    assert query.startswith("INSERT INTO uns_meta.metric_path_lineage")
    assert params == (77, "Group/Edge/Device/Metric", "Group/Edge/Device/NewMetric")
    assert counter.count == 1


@pytest.mark.unit
def test_apply_does_not_increment_counter_on_conflict() -> None:
    conn = _FakeConnection(responses=[[]])
    counter = _Counter()
    writer = LineageVersionWriter(conn, lineage_counter=counter)

    writer.apply(
        metric_id=88,
        new_uns_path="Group/Edge/Device/Metric",
        diff={},
        previous_uns_path="Group/Edge/Device/Metric-Old",
        changed_by="planner",
    )

    assert len(conn.executed) == 1
    query, _ = conn.executed[0]
    assert query.startswith("INSERT INTO uns_meta.metric_path_lineage")
    assert counter.count == 0
