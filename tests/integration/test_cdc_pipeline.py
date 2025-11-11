from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional

import pytest

try:
    from uns_metadata_sync.db import (
        Error,
        LogicalReplicationConnection,
        connect,
        dict_row,
        errors,
        sql,
    )
except ImportError:  # pragma: no cover - optional dependency
    Error = None  # type: ignore[assignment]
    LogicalReplicationConnection = None  # type: ignore[assignment]
    connect = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    errors = None  # type: ignore[assignment]
    sql = None  # type: ignore[assignment]

from uns_metadata_sync.cdc.checkpoint import InMemoryCheckpointStore
from uns_metadata_sync.cdc.logical_replication import (
    ChangeColumn,
    ChangeRecord,
    ReplicationStreamMessage,
)
from uns_metadata_sync.cdc.service import (
    CDCListenerMetrics,
    CDCListenerService,
    PostgresMetadataProvider,
    int_to_lsn,
)
from uns_metadata_sync.db.lineage_writers import LineageVersionWriter
from uns_metadata_sync.db.repository import (
    DevicePayload,
    MetadataRepository,
    MetricPayload,
    MetricPropertyPayload,
)
from uns_metadata_sync.migrations.runner import apply_migrations


pytestmark = pytest.mark.integration


@dataclass
class _CDCEnv:
    conn_params: Dict[str, object]
    slot_name: str
    dsn: str
    host: str
    port: int
    db_name: str
    db_user: str
    db_password: str


@pytest.fixture()
def cdc_environment() -> Iterable[_CDCEnv]:
    if connect is None or LogicalReplicationConnection is None:
        pytest.skip(
            "psycopg with replication extras is required for CDC integration test"
        )

    host = os.getenv("PGHOST", "localhost")
    port = int(os.getenv("PGPORT", "5432"))
    admin_user = os.getenv("PGUSER")
    admin_password = os.getenv("PGPASSWORD")

    if not admin_user or admin_password is None:
        pytest.skip("PGUSER and PGPASSWORD must be configured for CDC integration test")

    db_name = f"uns_meta_cdc_{uuid.uuid4().hex[:8]}"
    slot_name = f"uns_meta_slot_{uuid.uuid4().hex[:8]}"
    base_conn_kwargs = {
        "host": host,
        "port": port,
        "user": admin_user,
        "password": admin_password,
    }

    admin_conn = connect(dbname="uns_metadata", **base_conn_kwargs)
    admin_conn.autocommit = True
    try:
        admin_conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (db_name,),
        )
        admin_conn.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(db_name),
                sql.Identifier(admin_user),
            )
        )
    finally:
        admin_conn.close()

    slot_created = False
    try:
        with connect(dbname=db_name, **base_conn_kwargs) as conn:
            apply_migrations(conn=conn)

        with connect(dbname=db_name, **base_conn_kwargs) as repl_conn:
            repl_conn.autocommit = True
            try:
                repl_conn.execute(
                    "SELECT slot_name FROM pg_create_logical_replication_slot(%s, 'wal2json')",
                    (slot_name,),
                )
                slot_created = True
            except errors.UndefinedFile:
                pytest.skip(
                    "wal2json output plugin is not installed in the Postgres instance"
                )
            except Error as exc:
                pytest.skip(f"unable to create wal2json replication slot: {exc}")

        yield _CDCEnv(
            conn_params={**base_conn_kwargs, "dbname": db_name},
            slot_name=slot_name,
            dsn=(
                f"host={host} port={port} dbname={db_name} "
                f"user={admin_user} password={admin_password}"
            ),
            host=host,
            port=port,
            db_name=db_name,
            db_user=admin_user,
            db_password=admin_password,
        )
    finally:
        if connect is not None:
            if slot_created:
                with connect(dbname=db_name, **base_conn_kwargs) as conn:
                    conn.autocommit = True
                    try:
                        conn.execute(
                            "SELECT pg_drop_replication_slot(%s)",
                            (slot_name,),
                        )
                    except Error:
                        conn.rollback()
            with connect(dbname="postgres", **base_conn_kwargs) as cleanup:
                cleanup.autocommit = True
                cleanup.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                    (db_name,),
                )
                cleanup.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        sql.Identifier(db_name)
                    )
                )


class ManualClock:
    def __init__(self, start: Optional[float] = None) -> None:
        self._current = start if start is not None else time.monotonic()

    def advance(self, seconds: float) -> float:
        self._current += seconds
        return self._current

    def __call__(self) -> float:
        return self._current


def _lsn_to_int(value: str) -> int:
    upper, lower = value.split("/")
    return (int(upper, 16) << 32) + int(lower, 16)


def _normalize_wal2json_action(entry: Dict[str, object]) -> Optional[Dict[str, object]]:
    action = entry.get("action")
    kind_map = {"I": "insert", "U": "update", "D": "delete"}
    kind = kind_map.get(action)
    if kind is None:
        return None
    columns = entry.get("columns") or []
    column_names: List[str] = []
    column_values: List[object] = []
    for column in columns:
        if not isinstance(column, dict):
            continue
        name = column.get("name")
        if name is None:
            continue
        column_names.append(name)
        column_values.append(column.get("value"))
    change: Dict[str, object] = {
        "kind": kind,
        "schema": entry.get("schema"),
        "table": entry.get("table"),
        "columnnames": column_names,
        "columnvalues": column_values,
    }
    key_source = entry.get("identity") or entry.get("oldkeys") or entry.get("pk")
    key_names: List[str] = []
    key_values: List[object] = []
    if isinstance(key_source, dict):
        key_names = list(key_source.get("keynames") or [])
        key_values = list(key_source.get("keyvalues") or [])
    elif isinstance(key_source, list):
        for item in key_source:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if name is None:
                continue
            key_names.append(name)
            key_values.append(item.get("value"))
    if key_names:
        change["oldkeys"] = {"keynames": key_names, "keyvalues": key_values}
    return change


class Wal2JsonChangeDecoder:
    def decode(self, message: ReplicationStreamMessage) -> List[ChangeRecord]:
        payload = json.loads(message.data.decode("utf-8"))
        changes = payload.get("change", [])
        records: List[ChangeRecord] = []
        for entry in changes:
            schema = entry.get("schema")
            table = entry.get("table")
            relation = f"{schema}.{table}" if schema and table else table or ""
            column_names = entry.get("columnnames") or []
            column_values = entry.get("columnvalues") or []
            columns = [
                ChangeColumn(
                    name=name,
                    value=column_values[idx] if idx < len(column_values) else None,
                    type_oid=0,
                    flags={},
                )
                for idx, name in enumerate(column_names)
            ]
            oldkeys = entry.get("oldkeys") or {}
            key_names = oldkeys.get("keynames") or []
            key_values = oldkeys.get("keyvalues") or []
            old_columns = [
                ChangeColumn(
                    name=key_names[idx],
                    value=key_values[idx] if idx < len(key_values) else None,
                    type_oid=0,
                    flags={},
                )
                for idx in range(len(key_names))
            ] or None
            records.append(
                ChangeRecord(
                    kind=entry.get("kind", ""),
                    relation=relation,
                    columns=columns,
                    old_columns=old_columns,
                    lsn=message.lsn,
                    commit_timestamp=message.commit_timestamp,
                )
            )
        return records


def _wal2json_stream_factory(dsn: str, slot_name: str):
    options_sql = ", ".join(
        [
            "'include-types', '1'",
            "'include-pk', '1'",
            "'format-version', '2'",
            "'add-tables', 'uns_meta.metrics,uns_meta.metric_properties'",
        ]
    )
    query = f"""
        SELECT *
          FROM pg_logical_slot_get_changes(
                %s,
                %s,
                NULL,
                {options_sql}
          )
    """

    def _factory(start_lsn: Optional[int]) -> Iterator[ReplicationStreamMessage]:
        start_pos = int_to_lsn(start_lsn) if start_lsn is not None else None
        conn = connect(dsn)  # type: ignore[arg-type]
        conn.autocommit = True
        cur = conn.cursor()
        try:
            params = (slot_name, start_pos)
            while True:
                cur.execute(query, params)
                rows = cur.fetchall()
                if not rows:
                    break
                params = (slot_name, None)
                pending_changes: List[Dict[str, object]] = []
                commit_lsn: Optional[str] = None
                for change_lsn, _, raw_data in rows:
                    try:
                        entry = json.loads(raw_data)
                    except json.JSONDecodeError:
                        continue
                    action = entry.get("action")
                    if action == "B":
                        pending_changes = []
                        commit_lsn = None
                        continue
                    if action == "C":
                        commit_lsn = str(change_lsn)
                        if pending_changes:
                            payload = json.dumps({"change": pending_changes}).encode(
                                "utf-8"
                            )
                            yield ReplicationStreamMessage(
                                lsn=_lsn_to_int(commit_lsn),
                                data=payload,
                                commit_timestamp=time.time(),
                            )
                            pending_changes = []
                        continue
                    normalized = _normalize_wal2json_action(entry)
                    if normalized:
                        pending_changes.append(normalized)
        finally:
            try:
                cur.close()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    return _factory


def test_cdc_pipeline_emits_debounced_diff(cdc_environment: _CDCEnv) -> None:
    if connect is None or dict_row is None:
        pytest.skip("psycopg not installed")

    env = cdc_environment

    with connect(**env.conn_params) as conn:
        conn.row_factory = dict_row
        conn.execute("SET search_path TO uns_meta, public")
        repo = MetadataRepository(conn)

        device = repo.upsert_device(
            DevicePayload(
                group_id="Secil",
                country="PT",
                business_unit="Cement",
                plant="OUT",
                edge="Maceira-Edge",
                device="Kiln-K1",
                uns_path="Secil/OUT/Maceira-Edge/Kiln-K1",
            )
        ).record

        metric = repo.upsert_metric(
            MetricPayload(
                device_id=device["device_id"],
                name="kiln.temperature",
                uns_path="Secil/OUT/Maceira-Edge/Kiln-K1/kiln.temperature",
                datatype="double",
            )
        ).record

        repo.upsert_metric_property(
            MetricPropertyPayload(
                metric_id=metric["metric_id"],
                key="engineering_unit",
                type="string",
                value="C",
            )
        )

    diff_log: List[Dict[str, object]] = []
    metrics = CDCListenerMetrics(namespace="test")
    clock = ManualClock()
    metadata_provider = PostgresMetadataProvider(
        host=env.host,
        port=env.port,
        user=env.db_user,
        password=env.db_password,
        database=env.db_name,
        schema="uns_meta",
    )

    service = CDCListenerService(
        slot_name=env.slot_name,
        stream_factory=_wal2json_stream_factory(env.dsn, env.slot_name),
        decoder=Wal2JsonChangeDecoder(),
        metadata_provider=metadata_provider,
        diff_sink=diff_log.append,
        checkpoint_store=InMemoryCheckpointStore(),
        metrics=metrics,
        max_batch_messages=50,
        window_seconds=0.01,
        buffer_cap=16,
        idle_sleep_seconds=0.0,
        flush_interval_seconds=0.0,
        clock=clock,
        sleep=lambda _seconds: None,
    )

    diff_payload = {
        "properties": {
            "engineering_unit": {
                "old": "C",
                "new": "F",
            }
        }
    }

    with connect(**env.conn_params) as conn:
        conn.row_factory = dict_row
        conn.execute("SET search_path TO uns_meta, public")
        repo = MetadataRepository(conn)
        repo.upsert_metric_property(
            MetricPropertyPayload(
                metric_id=metric["metric_id"],
                key="engineering_unit",
                type="string",
                value="F",
            )
        )
        writer = LineageVersionWriter(conn)
        writer.apply(
            metric_id=metric["metric_id"],
            new_uns_path=metric["uns_path"],
            diff=diff_payload,
            previous_uns_path=metric["uns_path"],
            changed_by="integration-test",
        )
        version_row = conn.execute(
            """
            SELECT version_id, changed_at
              FROM uns_meta.metric_versions
             WHERE metric_id = %s
             ORDER BY version_id DESC
             LIMIT 1
            """,
            (metric["metric_id"],),
        ).fetchone()

    assert version_row is not None
    version_id = version_row["version_id"]

    try:
        processed = service.process_once()
        assert processed == 0

        clock.advance(0.5)
        flushed = service.force_flush()
        assert flushed == 1

        assert len(diff_log) == 1
        payload = diff_log[0]

        assert payload["metric_id"] == metric["metric_id"]
        assert payload["uns_path"] == metric["uns_path"]
        assert payload["canary_id"] == metric["canary_id"]
        assert payload["versions"] == [version_id]
        assert payload["changes"] == diff_payload

        metadata = payload["metadata"]
        assert isinstance(metadata, dict)
        assert metadata["event_ids"] == [f"{metric['metric_id']}:{version_id}"]
        assert metadata["latest_actor"] == "integration-test"
        assert metadata["debounce_span_seconds"] >= 0.0
        assert metadata["changed_at"].endswith("Z")

        metrics_snapshot = service.metrics.snapshot()
        assert metrics_snapshot["events_total"] == 1
        assert metrics_snapshot["payloads_total"] == 1
    finally:
        service.stop()
        metadata_provider.close()
