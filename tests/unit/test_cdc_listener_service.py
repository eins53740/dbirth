import pytest
from datetime import datetime, timezone

from uns_metadata_sync.cdc.checkpoint import InMemoryCheckpointStore
from uns_metadata_sync.cdc.debounce import DebounceBuffer
from uns_metadata_sync.cdc.diffing import DiffAccumulator
from uns_metadata_sync.cdc.logical_replication import (
    ChangeColumn,
    ChangeRecord,
    ReplicationStreamMessage,
)
from uns_metadata_sync.cdc.service import (
    CDCListenerMetrics,
    CDCListenerService,
    MetricIdentity,
    MetricVersionSnapshot,
)


class ManualClock:
    def __init__(self, start: float = 0.0) -> None:
        self._current = start

    def advance(self, seconds: float) -> float:
        self._current += seconds
        return self._current

    def __call__(self) -> float:
        return self._current


class StaticDecoder:
    def __init__(self, changes):
        self._changes = changes

    def decode(self, _message):
        return self._changes


class StubMetadataProvider:
    def __init__(self, identity, version_snapshot):
        self._identity = identity
        self._version_snapshot = version_snapshot
        self.calls = []

    def get_identity(self, metric_id):
        self.calls.append(("identity", metric_id))
        if self._identity and self._identity.metric_id == metric_id:
            return self._identity
        return None

    def get_version_snapshot(self, metric_id):
        self.calls.append(("version", metric_id))
        if self._version_snapshot and self._version_snapshot.metric_id == metric_id:
            return self._version_snapshot
        return None


@pytest.mark.unit
def test_cdc_listener_emits_debounced_payload():
    clock = ManualClock()
    metric_id = 42
    change = ChangeRecord(
        kind="update",
        relation="uns_meta.metric_properties",
        columns=[
            ChangeColumn(name="metric_id", value=metric_id, type_oid=23, flags={})
        ],
        lsn=100,
        commit_timestamp=clock(),
    )
    message = ReplicationStreamMessage(lsn=100, data=b"{}", commit_timestamp=clock())
    decoder = StaticDecoder([change])

    identity = MetricIdentity(
        metric_id=metric_id,
        uns_path="Secil/Portugal/Cement/Maceira/Kiln/T1",
        canary_id="Secil.Portugal.Cement.Maceira.Kiln.T1",
    )
    version_snapshot = MetricVersionSnapshot(
        metric_id=metric_id,
        version=7,
        actor="cdc-writer",
        changed_at=datetime(2025, 9, 1, 12, 0, tzinfo=timezone.utc),
        diff={"properties": {"displayHigh": 1800}},
        previous_version=6,
    )
    metadata_provider = StubMetadataProvider(identity, version_snapshot)
    emitted = []
    checkpoint_store = InMemoryCheckpointStore()
    buffer = DebounceBuffer(window_seconds=1, max_entries=10, clock=clock)

    service = CDCListenerService(
        slot_name="uns_meta_slot",
        stream_factory=lambda _lsn: iter([message]),
        decoder=decoder,
        metadata_provider=metadata_provider,
        diff_sink=emitted.append,
        checkpoint_store=checkpoint_store,
        debounce_buffer=buffer,
        diff_accumulator=DiffAccumulator(),
        metrics=CDCListenerMetrics(namespace="test"),
        max_batch_messages=10,
        window_seconds=1,
        buffer_cap=10,
        idle_sleep_seconds=0.0,
        flush_interval_seconds=0.0,
        clock=clock,
        sleep=lambda _seconds: None,
    )

    processed = service.process_once()
    assert processed == 0  # flush happens later

    clock.advance(2)
    flushed = service.force_flush()
    assert flushed == 1

    assert len(emitted) == 1
    payload = emitted[0]
    assert payload["uns_path"] == identity.uns_path
    assert payload["canary_id"] == identity.canary_id
    assert payload["versions"] == [version_snapshot.version]
    assert payload["changes"] == version_snapshot.diff
    assert payload["metadata"][
        "changed_at"
    ] == version_snapshot.changed_at.isoformat().replace("+00:00", "Z")
    assert checkpoint_store.load("uns_meta_slot") == 100

    metrics_snapshot = service.metrics.snapshot()
    assert metrics_snapshot["events_total"] == 1
    assert metrics_snapshot["payloads_total"] == 1


@pytest.mark.unit
def test_cdc_listener_skips_when_identity_missing():
    clock = ManualClock()
    metric_id = 99
    change = ChangeRecord(
        kind="update",
        relation="uns_meta.metrics",
        columns=[
            ChangeColumn(name="metric_id", value=metric_id, type_oid=23, flags={})
        ],
        lsn=200,
        commit_timestamp=clock(),
    )
    message = ReplicationStreamMessage(lsn=200, data=b"{}", commit_timestamp=clock())
    decoder = StaticDecoder([change])
    provider = StubMetadataProvider(None, None)
    emitted: list[dict] = []

    service = CDCListenerService(
        slot_name="slot",
        stream_factory=lambda _lsn: iter([message]),
        decoder=decoder,
        metadata_provider=provider,
        diff_sink=emitted.append,
        checkpoint_store=InMemoryCheckpointStore(),
        debounce_buffer=DebounceBuffer(window_seconds=1, max_entries=10, clock=clock),
        diff_accumulator=DiffAccumulator(),
        metrics=CDCListenerMetrics(namespace="test"),
        idle_sleep_seconds=0.0,
        flush_interval_seconds=0.0,
        clock=clock,
        sleep=lambda _seconds: None,
    )

    service.process_once()
    clock.advance(2)
    service.force_flush()

    assert emitted == []
    assert ("identity", metric_id) in provider.calls


@pytest.mark.unit
def test_cdc_listener_reset_resume_requires_expected():
    clock = ManualClock()
    checkpoint_store = InMemoryCheckpointStore()
    checkpoint_store.save("slot", 400)
    emitted: list[dict] = []
    buffer = DebounceBuffer(window_seconds=1, max_entries=10, clock=clock)

    service = CDCListenerService(
        slot_name="slot",
        stream_factory=lambda _lsn: iter([]),
        decoder=StaticDecoder([]),
        metadata_provider=StubMetadataProvider(None, None),
        diff_sink=emitted.append,
        checkpoint_store=checkpoint_store,
        debounce_buffer=buffer,
        diff_accumulator=DiffAccumulator(),
        metrics=CDCListenerMetrics(namespace="test"),
        idle_sleep_seconds=0.0,
        flush_interval_seconds=0.0,
        clock=clock,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(ValueError):
        service.reset_resume_position(expected_lsn=None)

    with pytest.raises(ValueError):
        service.reset_resume_position(expected_lsn=200)

    service.reset_resume_position(expected_lsn=400, new_lsn=150)
    assert checkpoint_store.load("slot") == 150
