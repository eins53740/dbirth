from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Sequence

from uns_metadata_sync.db import OperationalError
import pytest

from uns_metadata_sync.db.repository import (
    DevicePayload,
    MetadataRepository,
    MetricPayload,
    MetricPropertyPayload,
    RepositoryError,
)


class _FakeCursor:
    def __init__(self, rows: List[dict[str, Any]]):
        self._rows = rows
        self._index = 0

    def fetchone(self) -> Optional[dict[str, Any]]:
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return row
        return None

    def fetchall(self) -> List[dict[str, Any]]:
        remaining = self._rows[self._index :]
        self._index = len(self._rows)
        return remaining


class _FakeTransaction:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:  # pragma: no cover - unused
        return False


class _FakeConnection:
    def __init__(self, responses: Iterator[Any]):
        self._responses = responses
        self.executed = []
        self.row_factory = None

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction()

    def execute(self, query: str, params: Any) -> _FakeCursor:
        self.executed.append((query.strip().splitlines()[0], params))
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        return _FakeCursor(response)


@pytest.fixture
def device_payload() -> DevicePayload:
    return DevicePayload(
        group_id="SECIL.GROUP",
        country="PT",
        business_unit="Cement",
        plant="OUT",
        edge="EDGE-01",
        device="DEVICE-01",
        uns_path="SECIL.GROUP/EDGE-01/DEVICE-01",
    )


@pytest.mark.unit
def test_device_upsert_inserts_updates_and_noops(device_payload: DevicePayload) -> None:
    inserted_row = {
        "device_id": 1,
        "group_id": device_payload.group_id,
        "country": device_payload.country,
        "business_unit": device_payload.business_unit,
        "plant": device_payload.plant,
        "edge": device_payload.edge,
        "device": device_payload.device,
        "uns_path": device_payload.uns_path,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }
    updated_row = dict(inserted_row)
    updated_row["business_unit"] = "Aggregates"
    updated_row["updated_at"] = "2025-01-02T00:00:00Z"

    repo = MetadataRepository(
        _FakeConnection(
            iter(
                [
                    [],  # initial lookup
                    [],  # identity lookup
                    [inserted_row],  # insert
                    [inserted_row],  # noop lookup
                    [inserted_row],  # identity -> match
                    [updated_row],  # update returning
                ]
            )
        )
    )

    assert repo.upsert_device(device_payload).status == "inserted"
    assert repo.upsert_device(device_payload).status == "noop"

    updated_payload = DevicePayload(
        **{**device_payload.__dict__, "business_unit": "Aggregates"}
    )
    result = repo.upsert_device(updated_payload)
    assert result.status == "updated"
    assert result.record["business_unit"] == "Aggregates"


@pytest.mark.unit
def test_device_upsert_wraps_psycopg_errors(device_payload: DevicePayload) -> None:
    fake_error = OperationalError("forced failure")
    repo = MetadataRepository(_FakeConnection(iter([fake_error])))

    with pytest.raises(RepositoryError) as excinfo:
        repo.upsert_device(device_payload)

    assert "device upsert failed" in str(excinfo.value)


@pytest.fixture
def metric_payload() -> MetricPayload:
    return MetricPayload(
        device_id=1,
        name="temperature",
        uns_path="SECIL.GROUP/EDGE-01/DEVICE-01/temperature",
        datatype="double",
    )


@pytest.mark.unit
def test_metric_upsert_handles_insert_update_and_noop(
    metric_payload: MetricPayload,
) -> None:
    inserted_row = {
        "metric_id": 10,
        "device_id": metric_payload.device_id,
        "name": metric_payload.name,
        "uns_path": metric_payload.uns_path,
        "datatype": metric_payload.datatype,
        "canary_id": "SECIL.GROUP.EDGE-01.DEVICE-01.temperature",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }
    updated_row = dict(inserted_row)
    updated_row["datatype"] = "string"
    updated_row["updated_at"] = "2025-01-02T00:00:00Z"

    repo = MetadataRepository(
        _FakeConnection(
            iter(
                [
                    [],  # lookup by uns_path
                    [],  # identity lookup
                    [inserted_row],  # insert
                    [inserted_row],  # noop lookup
                    [inserted_row],  # update lookup by uns_path
                    [updated_row],
                ]
            )
        )
    )

    assert repo.upsert_metric(metric_payload).status == "inserted"
    assert repo.upsert_metric(metric_payload).status == "noop"

    updated_payload = MetricPayload(**{**metric_payload.__dict__, "datatype": "string"})
    result = repo.upsert_metric(updated_payload)
    assert result.status == "updated"
    assert result.record["datatype"] == "string"


@pytest.mark.unit
def test_upsert_metrics_bulk_inserts_and_updates(metric_payload: MetricPayload) -> None:
    class _BulkCursor:
        def __init__(self, conn: _FakeConnection, rows: List[dict[str, Any]]):
            self.conn = conn
            self.rows = rows
            self._index = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def execute(self, query: str, vars: Optional[Sequence[Any]] = None) -> None:
            self.conn.executed.append((query.strip().splitlines()[0], vars))

        def fetchall(self) -> List[dict[str, Any]]:
            return self.rows

    class _BulkConnection:
        def __init__(self, responses: Iterator[Any]):
            self._responses = responses
            self.executed = []
            self.row_factory = None

        def cursor(self, row_factory=None) -> _BulkCursor:
            return _BulkCursor(self, next(self._responses))

    payloads = [
        metric_payload,
        MetricPayload(
            device_id=1,
            name="pressure",
            uns_path="SECIL.GROUP/EDGE-01/DEVICE-01/pressure",
            datatype="float",
        ),
    ]

    id_map_response = [
        {"name": "temperature", "metric_id": 10},
        {"name": "pressure", "metric_id": 11},
    ]

    conn = _BulkConnection(iter([id_map_response]))
    repo = MetadataRepository(conn)

    id_map = repo.upsert_metrics_bulk(payloads)

    assert len(conn.executed) == 2
    insert_query, insert_params = conn.executed[0]
    assert "INSERT INTO uns_meta.metrics" in insert_query
    assert len(insert_params) == 8

    select_query, select_params = conn.executed[1]
    assert "SELECT name, metric_id FROM uns_meta.metrics" in select_query
    assert select_params[0] == 1
    assert "temperature" in select_params
    assert "pressure" in select_params
    assert id_map == {"temperature": 10, "pressure": 11}


@pytest.mark.unit
def test_upsert_metrics_bulk_empty_list() -> None:
    repo = MetadataRepository(_FakeConnection(iter([])))
    assert repo.upsert_metrics_bulk([]) == {}


@pytest.mark.unit
def test_upsert_metrics_bulk_wraps_psycopg_errors(
    metric_payload: MetricPayload,
) -> None:
    class _ErrorConnection:
        def __init__(self):
            self.row_factory = None

        def cursor(self, row_factory=None):
            raise OperationalError("forced failure")

    repo = MetadataRepository(_ErrorConnection())

    with pytest.raises(RepositoryError) as excinfo:
        repo.upsert_metrics_bulk([metric_payload])

    assert "metric bulk upsert failed" in str(excinfo.value)


@pytest.fixture
def metric_property_payload() -> MetricPropertyPayload:
    return MetricPropertyPayload(
        metric_id=10, key="engineering_unit", type="string", value="C"
    )


@pytest.mark.unit
def test_metric_property_upsert_insert_update_noop(
    metric_property_payload: MetricPropertyPayload,
) -> None:
    inserted_row = {
        "metric_id": metric_property_payload.metric_id,
        "key": metric_property_payload.key,
        "type": metric_property_payload.type,
        "value_int": None,
        "value_long": None,
        "value_float": None,
        "value_double": None,
        "value_string": "C",
        "value_bool": None,
        "updated_at": "2025-01-01T00:00:00Z",
    }
    updated_row = dict(inserted_row)
    updated_row["value_string"] = "F"
    updated_row["updated_at"] = "2025-01-02T00:00:00Z"

    repo = MetadataRepository(
        _FakeConnection(
            iter(
                [
                    [],  # lookup
                    [inserted_row],  # insert
                    [inserted_row],  # noop lookup
                    [inserted_row],  # update lookup
                    [updated_row],
                ]
            )
        )
    )

    assert repo.upsert_metric_property(metric_property_payload).status == "inserted"
    assert repo.upsert_metric_property(metric_property_payload).status == "noop"

    updated_payload = MetricPropertyPayload(
        metric_id=metric_property_payload.metric_id,
        key=metric_property_payload.key,
        type="string",
        value="F",
    )
    result = repo.upsert_metric_property(updated_payload)
    assert result.status == "updated"
    assert result.record["value_string"] == "F"


@pytest.mark.unit
def test_metric_property_upsert_requires_supported_type(
    metric_property_payload: MetricPropertyPayload,
) -> None:
    invalid_payload = MetricPropertyPayload(
        metric_id=metric_property_payload.metric_id,
        key="unsupported",
        type="json",
        value={"a": 1},
    )
    repo = MetadataRepository(_FakeConnection(iter([])))

    with pytest.raises(RepositoryError) as excinfo:
        repo.upsert_metric_property(invalid_payload)

    assert "invalid property type" in str(excinfo.value)


@pytest.mark.unit
def test_metric_property_bulk_upsert_batches() -> None:
    class _BulkSelectCursor:
        def __init__(self, rows: List[dict[str, Any]]):
            self._rows = rows

        def fetchall(self) -> List[dict[str, Any]]:
            return self._rows

    class _BulkCursor:
        def __init__(self, conn):
            self.conn = conn
            self.rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def execute(self, query: str, vars: Optional[Sequence[Any]] = None) -> None:
            row_params = list(vars) if vars else []
            self.conn.insert_calls.append((query, list(vars) if vars else []))
            # Each metric property row has 9 columns.
            self.rowcount = len(row_params) // 9

    class _BulkTransaction:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            self.conn.transaction_calls += 1
            return None

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class _BulkConnection:
        def __init__(self, select_responses: Iterator[List[dict[str, Any]]]):
            self.row_factory = None
            self.transaction_calls = 0
            self.select_responses = select_responses
            self.select_queries: List[tuple[str, Any]] = []
            self.insert_calls: List[tuple[str, List[Any]]] = []

        def transaction(self):
            return _BulkTransaction(self)

        def execute(self, query: str, params: Any) -> _BulkSelectCursor:
            self.select_queries.append((query.strip(), params))
            return _BulkSelectCursor(next(self.select_responses))

        def cursor(self, row_factory=None):
            assert row_factory is None
            return _BulkCursor(self)

    conn = _BulkConnection(iter([[]]))
    repo = MetadataRepository(conn)

    payloads = [
        MetricPropertyPayload(metric_id=1, key="name", type="string", value="value"),
        MetricPropertyPayload(metric_id=1, key="count", type="int", value=5),
    ]

    affected = repo.upsert_metric_properties_bulk(payloads, batch_size=1)

    assert affected == 2
    assert conn.transaction_calls == 1
    assert len(conn.select_queries) == 0
    assert len(conn.insert_calls) == 2

    first_query, string_params = conn.insert_calls[0]
    _, int_params = conn.insert_calls[1]
    assert "INSERT INTO uns_meta.metric_properties AS mp" in first_query
    assert "WHERE mp.type IS DISTINCT FROM EXCLUDED.type" in first_query

    assert string_params == [
        1,
        "name",
        "string",
        None,
        None,
        None,
        None,
        "value",
        None,
    ]
    assert int_params == [
        1,
        "count",
        "int",
        5,
        None,
        None,
        None,
        None,
        None,
    ]


@pytest.mark.unit
def test_metric_property_bulk_upsert_skips_unchanged_rows() -> None:
    class _Connection:
        def __init__(self):
            self.row_factory = None
            self.calls: List[List[Any]] = []

        def transaction(self):
            return _FakeTransaction()

        def cursor(self, row_factory=None):
            conn = self

            class _Cursor:
                def __enter__(self_inner):
                    self_inner.rowcount = 0
                    return self_inner

                def __exit__(self_inner, exc_type, exc, tb) -> bool:
                    return False

                def execute(
                    self_inner, _query: str, vars: Optional[Sequence[Any]] = None
                ):
                    params = list(vars) if vars else []
                    conn.calls.append(params)
                    # Simulate ON CONFLICT update skipped (no change).
                    self_inner.rowcount = 0

            return _Cursor()

    conn = _Connection()
    repo = MetadataRepository(conn)

    payloads = [
        MetricPropertyPayload(metric_id=1, key="unit", type="string", value="C")
    ]

    affected = repo.upsert_metric_properties_bulk(payloads)
    assert affected == 0
    assert len(conn.calls) == 1
    assert conn.calls[0] == [
        1,
        "unit",
        "string",
        None,
        None,
        None,
        None,
        "C",
        None,
    ]


@pytest.mark.unit
def test_metric_property_bulk_upsert_updates_only_changes() -> None:
    existing_state: Dict[str, tuple[str, Any]] = {
        "unit": ("string", "C"),
        "precision": ("int", 2),
    }

    class _BulkCursor:
        def __init__(self):
            self.calls: List[List[Any]] = []
            self.rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def execute(self, _query: str, vars: Optional[Sequence[Any]] = None) -> None:
            params = list(vars) if vars else []
            self.calls.append(params)
            changed = 0
            for i in range(0, len(params), 9):
                (
                    _metric_id,
                    key,
                    value_type,
                    value_int,
                    value_long,
                    value_float,
                    value_double,
                    value_string,
                    value_bool,
                ) = params[i : i + 9]
                if value_type == "string":
                    new_value = value_string
                elif value_type == "int":
                    new_value = value_int
                elif value_type == "long":
                    new_value = value_long
                elif value_type == "float":
                    new_value = value_float
                elif value_type == "double":
                    new_value = value_double
                elif value_type == "boolean":
                    new_value = value_bool
                else:
                    new_value = None

                previous = existing_state.get(key)
                if previous != (value_type, new_value):
                    changed += 1
                    existing_state[key] = (value_type, new_value)

            self.rowcount = changed

    class _Connection:
        def __init__(self):
            self.row_factory = None
            self.cursor_obj = _BulkCursor()

        def transaction(self):
            return _FakeTransaction()

        def cursor(self, row_factory=None):
            return self.cursor_obj

    conn = _Connection()
    repo = MetadataRepository(conn)

    payloads = [
        MetricPropertyPayload(metric_id=1, key="unit", type="string", value="C"),
        MetricPropertyPayload(metric_id=1, key="precision", type="int", value=4),
        MetricPropertyPayload(metric_id=1, key="display", type="boolean", value=True),
    ]

    affected = repo.upsert_metric_properties_bulk(payloads, batch_size=2)
    assert affected == 2  # precision + display
    assert len(conn.cursor_obj.calls) == 2

    first_params, second_params = conn.cursor_obj.calls
    first_chunks = [first_params[i : i + 9] for i in range(0, len(first_params), 9)]
    second_chunks = [second_params[i : i + 9] for i in range(0, len(second_params), 9)]

    assert first_chunks == [
        [1, "unit", "string", None, None, None, None, "C", None],
        [1, "precision", "int", 4, None, None, None, None, None],
    ]
    assert second_chunks == [
        [1, "display", "boolean", None, None, None, None, None, True],
    ]


@pytest.mark.unit
def test_metric_property_bulk_upsert_empty_list() -> None:
    repo = MetadataRepository(_FakeConnection(iter([])))
    assert repo.upsert_metric_properties_bulk([]) == 0
