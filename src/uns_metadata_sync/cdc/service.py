"""CDC listener service coordinating logical replication, debouncing, and diff emission."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Protocol

from ..db import (
    Connection,
    Json,
    Jsonb,
    LogicalReplicationConnection,
    connect,
    dict_row,
)

from ..config import Settings
from .checkpoint import InMemoryCheckpointStore, PersistentCheckpointStore
from .debounce import DebounceBuffer, DebounceMetrics
from .diffing import DiffAccumulator, DiffEvent
from .logical_replication import (
    ChangeColumn,
    ChangeDecoder,
    ChangeRecord,
    CheckpointStore,
    ExponentialBackoff,
    LogicalReplicationClient,
    ReplicationStreamMessage,
)

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from prometheus_client import Counter, Gauge
except Exception:  # noqa: BLE001 - any import failure should fallback silently
    Counter = None  # type: ignore[assignment]
    Gauge = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Metadata lookups


@dataclass(frozen=True)
class MetricIdentity:
    metric_id: int
    uns_path: str
    canary_id: str
    device_id: Optional[int] = None


@dataclass(frozen=True)
class MetricVersionSnapshot:
    metric_id: int
    version: int
    actor: str
    changed_at: datetime
    diff: Dict[str, object]
    previous_version: Optional[int] = None


class MetricMetadataProvider(Protocol):
    """Resolves metric metadata used to build CDC diff events."""

    def get_identity(self, metric_id: int) -> Optional[MetricIdentity]: ...

    def get_version_snapshot(
        self, metric_id: int
    ) -> Optional[MetricVersionSnapshot]: ...


class PostgresMetadataProvider:
    """Metadata provider backed by a PostgreSQL connection."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        schema: str,
        connect_timeout: float = 5.0,
    ) -> None:
        self._schema = schema
        self._conn_kwargs = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "dbname": database,
            "connect_timeout": int(connect_timeout),
        }
        self._conn: Optional[Connection] = None

    def _ensure_conn(self) -> Connection:
        if self._conn is not None and not self._conn.closed:
            return self._conn
        conn = connect(**self._conn_kwargs)
        conn.autocommit = True
        conn.row_factory = dict_row
        self._conn = conn
        return conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        self._conn = None

    def get_identity(self, metric_id: int) -> Optional[MetricIdentity]:
        conn = self._ensure_conn()
        row = conn.execute(
            f"""
            SELECT metric_id, device_id, uns_path, canary_id
              FROM {self._schema}.metrics
             WHERE metric_id = %s
            """,
            (metric_id,),
        ).fetchone()
        if not row:
            return None
        return MetricIdentity(
            metric_id=row["metric_id"],
            device_id=row.get("device_id"),
            uns_path=row["uns_path"],
            canary_id=row["canary_id"],
        )

    def get_version_snapshot(self, metric_id: int) -> Optional[MetricVersionSnapshot]:
        conn = self._ensure_conn()
        rows = conn.execute(
            f"""
            SELECT version_id, changed_by, changed_at, diff
              FROM {self._schema}.metric_versions
             WHERE metric_id = %s
             ORDER BY version_id DESC
             LIMIT 2
            """,
            (metric_id,),
        ).fetchall()
        if not rows:
            return None

        latest = rows[0]
        previous_version = rows[1]["version_id"] if len(rows) > 1 else None
        diff_payload = _normalize_diff(latest["diff"])
        if not diff_payload:
            return None
        return MetricVersionSnapshot(
            metric_id=metric_id,
            version=latest["version_id"],
            actor=latest["changed_by"],
            changed_at=latest["changed_at"],
            diff=diff_payload,
            previous_version=previous_version,
        )


def _normalize_diff(raw: object) -> Dict[str, object]:
    if raw is None:
        return {}
    if isinstance(raw, (Json, Jsonb)):
        return dict(raw.value or {})
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("diff payload not valid JSON: %s", raw)
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}
    return {}


# ---------------------------------------------------------------------------
# Metrics helpers


class _FallbackCounter:
    def __init__(self) -> None:
        self.value = 0.0

    def inc(self, amount: float = 1.0) -> None:
        self.value += amount


class _FallbackGauge:
    def __init__(self) -> None:
        self.value = 0.0

    def set(self, value: float) -> None:
        self.value = value


class CDCListenerMetrics:
    """Wraps Prometheus-style counters with fallback behaviour for tests."""

    def __init__(self, namespace: str = "uns_metadata_sync") -> None:
        metric_prefix = f"{namespace}_cdc"
        self._records = self._build_counter(
            f"{metric_prefix}_records_total", "CDC change records processed"
        )
        self._events = self._build_counter(
            f"{metric_prefix}_events_total", "CDC diff events generated"
        )
        self._payloads = self._build_counter(
            f"{metric_prefix}_payloads_total", "CDC payloads emitted downstream"
        )
        self._errors = self._build_counter(
            f"{metric_prefix}_errors_total", "CDC processing errors"
        )
        self._reconnects = self._build_counter(
            f"{metric_prefix}_reconnects_total", "CDC reconnect attempts"
        )
        self._drops = self._build_counter(
            f"{metric_prefix}_drops_total", "CDC debounce drops due to buffer cap"
        )
        self._emitted = self._build_counter(
            f"{metric_prefix}_emitted_total", "CDC debounce flush count"
        )
        self._buffer_depth = self._build_gauge(
            f"{metric_prefix}_buffer_depth", "CDC debounce buffer depth"
        )
        self._fallback_snapshot: Dict[str, float] = defaultdict(float)

    def _build_counter(self, name: str, documentation: str):
        if Counter is None:
            counter = _FallbackCounter()
        else:  # pragma: no cover - exercised only when prometheus_client installed
            counter = Counter(name, documentation)
        return counter

    def _build_gauge(self, name: str, documentation: str):
        if Gauge is None:
            gauge = _FallbackGauge()
        else:  # pragma: no cover
            gauge = Gauge(name, documentation)
        return gauge

    def inc_records(self, amount: int) -> None:
        if amount <= 0:
            return
        self._records.inc(amount)  # type: ignore[call-arg]
        self._fallback_snapshot["records_total"] += amount

    def inc_events(self, amount: int = 1) -> None:
        if amount <= 0:
            return
        self._events.inc(amount)  # type: ignore[call-arg]
        self._fallback_snapshot["events_total"] += amount

    def inc_payloads(self, amount: int = 1) -> None:
        if amount <= 0:
            return
        self._payloads.inc(amount)  # type: ignore[call-arg]
        self._fallback_snapshot["payloads_total"] += amount

    def inc_errors(self, amount: int = 1) -> None:
        if amount <= 0:
            return
        self._errors.inc(amount)  # type: ignore[call-arg]
        self._fallback_snapshot["errors_total"] += amount

    def inc_reconnects(self, amount: int = 1) -> None:
        if amount <= 0:
            return
        self._reconnects.inc(amount)  # type: ignore[call-arg]
        self._fallback_snapshot["reconnects_total"] += amount

    def inc_drops(self, amount: int = 1) -> None:
        if amount <= 0:
            return
        self._drops.inc(amount)  # type: ignore[call-arg]
        self._fallback_snapshot["drops_total"] += amount

    def inc_emitted(self, amount: int = 1) -> None:
        if amount <= 0:
            return
        self._emitted.inc(amount)  # type: ignore[call-arg]
        self._fallback_snapshot["debounce_flush_total"] += amount

    def set_buffer_depth(self, value: float) -> None:
        self._buffer_depth.set(value)  # type: ignore[call-arg]
        self._fallback_snapshot["buffer_depth"] = value

    def snapshot(self) -> Dict[str, float]:
        return dict(self._fallback_snapshot)

    def debounce_metrics(self) -> "DebounceMetricsAdapter":
        return DebounceMetricsAdapter(self)


class DebounceMetricsAdapter(DebounceMetrics):
    """Adapter bridging DebounceBuffer metrics to CDCListenerMetrics."""

    def __init__(self, metrics: CDCListenerMetrics) -> None:
        super().__init__()
        self._metrics = metrics

    def inc(self, name: str, value: int = 1) -> None:  # type: ignore[override]
        super().inc(name, value)
        if name == "dropped":
            self._metrics.inc_drops(value)
        elif name == "emitted":
            self._metrics.inc_emitted(value)

    def set_gauge(self, name: str, value: float) -> None:  # type: ignore[override]
        super().set_gauge(name, value)
        if name == "buffer_depth":
            self._metrics.set_buffer_depth(value)


# ---------------------------------------------------------------------------
# CDC listener service


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class CDCListenerService:
    """Orchestrates logical replication, diff aggregation, and debounce emission."""

    def __init__(
        self,
        *,
        slot_name: str,
        stream_factory: Callable[[Optional[int]], Iterable[ReplicationStreamMessage]],
        decoder: ChangeDecoder,
        metadata_provider: MetricMetadataProvider,
        diff_sink: Callable[[Dict[str, object]], None],
        checkpoint_store: Optional[CheckpointStore] = None,
        debounce_buffer: Optional[DebounceBuffer] = None,
        diff_accumulator: Optional[DiffAccumulator] = None,
        metrics: Optional[CDCListenerMetrics] = None,
        max_batch_messages: int = 500,
        window_seconds: float = 180.0,
        buffer_cap: int = 1000,
        idle_sleep_seconds: float = 1.0,
        flush_interval_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._metadata_provider = metadata_provider
        self._diff_sink = diff_sink
        self._clock = clock
        self._sleep = sleep
        self._idle_sleep = idle_sleep_seconds
        self._flush_interval = flush_interval_seconds
        self._max_batch_messages = max_batch_messages
        self._stop_event = Event()
        self._slot_name = slot_name
        self._metrics = metrics or CDCListenerMetrics()
        self._debounce_buffer = debounce_buffer or DebounceBuffer(
            window_seconds=window_seconds,
            max_entries=buffer_cap,
            clock=self._clock,
            metrics=self._metrics.debounce_metrics(),
        )
        self._diff_accumulator = diff_accumulator or DiffAccumulator()
        self._checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self._backoff = ExponentialBackoff(
            base_interval=0.5,
            multiplier=2.0,
            max_interval=30.0,
            max_attempts=None,
        )
        self._client = LogicalReplicationClient(
            slot_name=slot_name,
            stream_factory=stream_factory,
            decoder=decoder,
            checkpoint_store=self._checkpoint_store,
            handler=self._handle_change,
            checkpoint_interval=max(1, max_batch_messages // 2),
            backoff=self._backoff,
        )
        self._last_flush_ts = self._clock()

    @property
    def metrics(self) -> CDCListenerMetrics:
        return self._metrics

    def stop(self) -> None:
        self._stop_event.set()
        self.force_flush()

    def reset_resume_position(
        self,
        *,
        expected_lsn: Optional[int],
        new_lsn: Optional[int] = None,
        force: bool = False,
    ) -> None:
        """Manually reset the replication checkpoint with guardrails."""
        self._client.reset_checkpoint(
            expected_lsn=expected_lsn,
            new_lsn=new_lsn,
            force=force,
        )

    def run_forever(self) -> None:
        while not self._stop_event.is_set():
            self.process_once()

    def process_once(self) -> int:
        try:
            processed = self._client.process(max_messages=self._max_batch_messages)
            self._metrics.inc_records(processed)
        except Exception:  # noqa: BLE001
            delay = self._client.last_error_delay or self._backoff.next_delay()
            self._metrics.inc_errors()
            logger.exception("cdc processing failed - retrying in %.2fs", delay)
            self._sleep(delay)
            return 0

        emitted = self._flush_ready()

        if processed == 0 and emitted == 0:
            self._sleep(self._idle_sleep)
        return emitted

    def force_flush(self) -> int:
        return self._flush_ready(force=True)

    def _flush_ready(self, *, force: bool = False) -> int:
        now = self._clock()
        if not force and now - self._last_flush_ts < self._flush_interval:
            return 0
        if force:
            ready = self._debounce_buffer.flush_due(
                now=now + self._debounce_buffer.window_seconds
            )
        else:
            ready = self._debounce_buffer.flush_due(now=now)
        emitted = 0
        for entry in ready:
            snapshot = self._diff_accumulator.pop(entry["metric"])
            if not snapshot:
                continue
            payload = self._build_payload(entry, snapshot)
            try:
                self._diff_sink(payload)
            except Exception:  # noqa: BLE001 - sink errors should not stop CDC
                logger.exception("diff sink raised error")
                self._metrics.inc_errors()
                continue
            emitted += 1
            self._metrics.inc_payloads()
        if force or emitted:
            self._last_flush_ts = now
        return emitted

    def _build_payload(
        self,
        buffer_entry: Dict[str, object],
        snapshot: Dict[str, object],
    ) -> Dict[str, object]:
        extras = buffer_entry.get("extras", {}) or {}
        metadata = dict(snapshot.get("metadata", {}))
        metadata.update(
            {
                "event_ids": buffer_entry.get("event_ids", []),
                "debounce_first_seen": buffer_entry.get("first_seen"),
                "debounce_last_update": buffer_entry.get("last_update"),
            }
        )
        changed_at = extras.get("changed_at")
        if isinstance(changed_at, datetime):
            metadata["changed_at"] = _format_timestamp(changed_at)
        span = (buffer_entry.get("last_update", 0.0) or 0.0) - (
            buffer_entry.get("first_seen", 0.0) or 0.0
        )
        metadata["debounce_span_seconds"] = max(span, 0.0)
        payload = {
            "metric_id": extras.get("metric_id"),
            "uns_path": snapshot.get("uns_path"),
            "canary_id": extras.get("canary_id"),
            "versions": snapshot.get("versions", []),
            "metadata": metadata,
            "changes": snapshot.get("changes", {}),
        }
        return payload

    def _handle_change(self, change: ChangeRecord) -> None:
        metric_id = self._extract_metric_id(change)
        if metric_id is None:
            return
        identity = self._metadata_provider.get_identity(metric_id)
        if identity is None:
            logger.debug("metric %s missing from metadata store", metric_id)
            return
        version_snapshot = self._metadata_provider.get_version_snapshot(metric_id)
        if version_snapshot is None:
            return
        event = DiffEvent(
            event_id=f"{metric_id}:{version_snapshot.version}",
            uns_path=identity.uns_path,
            version=version_snapshot.version,
            actor=version_snapshot.actor,
            changes=dict(version_snapshot.diff),
            timestamp=_format_timestamp(version_snapshot.changed_at),
        )
        applied = self._diff_accumulator.apply(event)
        if not applied:
            return
        now = self._clock()
        self._debounce_buffer.add(
            metric_key=identity.uns_path,
            diff=dict(version_snapshot.diff),
            version=version_snapshot.version,
            actor=version_snapshot.actor,
            event_id=event.event_id,
            timestamp=now,
            extras={
                "metric_id": metric_id,
                "canary_id": identity.canary_id,
                "changed_at": version_snapshot.changed_at,
            },
        )
        self._metrics.inc_events()

    @staticmethod
    def _extract_metric_id(change: ChangeRecord) -> Optional[int]:
        for column in change.columns:
            if column.name == "metric_id":
                return int(column.value)
        if change.old_columns:
            for column in change.old_columns:
                if column.name == "metric_id":
                    return int(column.value)
        return None


# ---------------------------------------------------------------------------
# Factory helpers


def build_cdc_listener(
    settings: Settings,
    *,
    diff_sink: Callable[[Dict[str, object]], None],
    stream_factory: Optional[
        Callable[[Optional[int]], Iterable[ReplicationStreamMessage]]
    ] = None,
    decoder: Optional[ChangeDecoder] = None,
    checkpoint_store: Optional[CheckpointStore] = None,
    metadata_provider: Optional[MetricMetadataProvider] = None,
    metrics: Optional[CDCListenerMetrics] = None,
) -> CDCListenerService:
    """Construct a CDC listener using application settings."""

    if not settings.cdc_enabled:
        raise ValueError("CDC is disabled via configuration")

    provider = metadata_provider or PostgresMetadataProvider(
        host=settings.pg_replication_host,
        port=settings.pg_replication_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.pg_replication_database,
        schema=settings.db_schema,
    )

    if decoder is None:
        decoder = JsonChangeDecoder()

    if stream_factory is None:
        stream_factory = create_pgoutput_stream_factory(settings)

    store = checkpoint_store
    if store is None:
        if settings.cdc_checkpoint_backend == "file":
            store = PersistentCheckpointStore(
                settings.cdc_resume_path, fsync=settings.cdc_resume_fsync
            )
        else:
            store = InMemoryCheckpointStore()

    return CDCListenerService(
        slot_name=settings.cdc_slot,
        stream_factory=stream_factory,
        decoder=decoder,
        metadata_provider=provider,
        diff_sink=diff_sink,
        checkpoint_store=store,
        metrics=metrics,
        max_batch_messages=settings.cdc_max_batch_messages,
        window_seconds=settings.cdc_window_seconds,
        buffer_cap=settings.cdc_buffer_cap,
        idle_sleep_seconds=settings.cdc_idle_sleep_seconds,
        flush_interval_seconds=settings.cdc_flush_interval_seconds,
    )


def create_pgoutput_stream_factory(
    settings: Settings,
) -> Callable[[Optional[int]], Iterable[ReplicationStreamMessage]]:
    """Create a stream factory backed by PostgreSQL logical replication.

    This implementation relies on psycopg replication extras. If they are not installed,
    a RuntimeError is raised with guidance on enabling the dependency.
    """

    dsn = (
        f"host={settings.pg_replication_host} "
        f"port={settings.pg_replication_port} "
        f"dbname={settings.pg_replication_database} "
        f"user={settings.pg_replication_user} "
        f"password={settings.pg_replication_password} "
        f"sslmode={settings.pg_replication_sslmode}"
    )
    slot_name = settings.cdc_slot
    publication = settings.cdc_publication
    plugin = settings.cdc_replication_plugin.lower()

    def _factory(start_lsn: Optional[int]) -> Iterator[ReplicationStreamMessage]:
        start_pos = int_to_lsn(start_lsn) if start_lsn else None
        conn = LogicalReplicationConnection.connect(dsn)
        cur = conn.cursor()
        options: Dict[str, str] = {}
        if plugin == "pgoutput":
            options = {
                "proto_version": "1",
                "publication_names": publication,
            }
        elif plugin != "wal2json":
            logger.debug(
                "logical replication plugin %s does not have explicit options configured",
                plugin,
            )
        start_kwargs = {
            "slot_name": slot_name,
            "decode": False,
        }
        if options:
            start_kwargs["options"] = options
        if start_pos is not None:
            start_kwargs["start_lsn"] = start_pos
        cur.start_replication(**start_kwargs)
        try:
            while True:
                message = cur.read_message()
                if message is None:
                    time.sleep(0.1)
                    continue
                payload = bytes(message.payload)
                commit_time = getattr(message, "commit_time", None)
                commit_ts = (
                    commit_time.timestamp() if commit_time is not None else time.time()
                )
                yield ReplicationStreamMessage(
                    lsn=int(message.data_start),
                    data=payload,
                    commit_timestamp=commit_ts,
                )
                cur.send_feedback(flush_lsn=message.data_start)
        except GeneratorExit:
            # Allow the generator to be closed cleanly by the caller.
            return
        finally:
            cur.close()
            conn.close()

    return _factory


def int_to_lsn(value: int) -> str:
    upper = value >> 32
    lower = value & 0xFFFFFFFF
    return f"{upper:X}/{lower:X}"


class JsonChangeDecoder:
    """Fallback decoder expecting JSON payloads (e.g. for tests or wal2json)."""

    def decode(self, message: ReplicationStreamMessage) -> List[ChangeRecord]:
        try:
            payload = json.loads(message.data.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("replication payload is not valid JSON") from exc
        items: List[dict] = []
        if isinstance(payload, dict):
            changes = payload.get("change")
            if isinstance(changes, list):
                items.extend(entry for entry in changes if isinstance(entry, dict))
            else:
                items.append(payload)
        elif isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, dict):
                    changes = entry.get("change")
                    if isinstance(changes, list):
                        items.extend(
                            change for change in changes if isinstance(change, dict)
                        )
                    else:
                        items.append(entry)
        else:
            return []

        if not items:
            return []

        decoded: List[ChangeRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_columns = item.get("columns")
            columns: List[ChangeColumn] = []
            if isinstance(raw_columns, list):
                for col in raw_columns:
                    if not isinstance(col, dict) or "name" not in col:
                        continue
                    columns.append(
                        ChangeColumn(
                            name=str(col["name"]),
                            value=col.get("value"),
                            type_oid=col.get("type_oid", 0) or 0,
                            flags=col.get("flags", {}) or {},
                        )
                    )
            else:
                names = item.get("columnnames") or []
                values = item.get("columnvalues") or []
                types = item.get("columntypes") or []
                for index, name in enumerate(names):
                    value = values[index] if index < len(values) else None
                    type_name = types[index] if index < len(types) else None
                    columns.append(
                        ChangeColumn(
                            name=str(name),
                            value=value,
                            type_oid=0,
                            flags={"type_name": type_name} if type_name else {},
                        )
                    )
            raw_old = item.get("old_columns")
            old_columns: List[ChangeColumn] | None = None
            if isinstance(raw_old, list):
                tmp: List[ChangeColumn] = []
                for col in raw_old:
                    if not isinstance(col, dict) or "name" not in col:
                        continue
                    tmp.append(
                        ChangeColumn(
                            name=str(col["name"]),
                            value=col.get("value"),
                            type_oid=col.get("type_oid", 0) or 0,
                            flags=col.get("flags", {}) or {},
                        )
                    )
                old_columns = tmp or None
            elif isinstance(item.get("oldkeys"), dict):
                keys = item["oldkeys"]
                names = keys.get("keynames") or []
                values = keys.get("keyvalues") or []
                types = keys.get("keytypes") or []
                tmp: List[ChangeColumn] = []
                for index, name in enumerate(names):
                    value = values[index] if index < len(values) else None
                    type_name = types[index] if index < len(types) else None
                    tmp.append(
                        ChangeColumn(
                            name=str(name),
                            value=value,
                            type_oid=0,
                            flags={"type_name": type_name} if type_name else {},
                        )
                    )
                old_columns = tmp or None

            relation = item.get("relation") or ""
            if not relation:
                schema = item.get("schema")
                table = item.get("table")
                if schema and table:
                    relation = f"{schema}.{table}"
            decoded.append(
                ChangeRecord(
                    kind=item.get("kind", "update"),
                    relation=relation,
                    columns=columns,
                    old_columns=old_columns,
                    lsn=message.lsn,
                    commit_timestamp=message.commit_timestamp,
                )
            )
        return decoded


__all__ = [
    "CDCListenerMetrics",
    "CDCListenerService",
    "JsonChangeDecoder",
    "MetricIdentity",
    "MetricMetadataProvider",
    "MetricVersionSnapshot",
    "PostgresMetadataProvider",
    "build_cdc_listener",
    "create_pgoutput_stream_factory",
    "int_to_lsn",
]
