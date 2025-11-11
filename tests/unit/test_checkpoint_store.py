import json

import pytest

from uns_metadata_sync.cdc.checkpoint import PersistentCheckpointStore
from uns_metadata_sync.cdc.logical_replication import (
    ChangeColumn,
    ChangeRecord,
    LogicalReplicationClient,
    ReplicationStreamMessage,
)


class _SequentialDecoder:
    def __init__(self, batches):
        self._batches = list(batches)
        self._index = 0

    def decode(self, _message):
        batch = self._batches[self._index]
        self._index += 1
        return batch


class _RecordingStream:
    def __init__(self, batches):
        self._batches = list(batches)
        self.starts: list[int | None] = []

    def factory(self, start_lsn):
        self.starts.append(start_lsn)
        batch = self._batches.pop(0)
        return iter(batch)


def _build_change(lsn: int) -> ChangeRecord:
    return ChangeRecord(
        kind="update",
        relation="uns_meta.metrics",
        columns=[ChangeColumn(name="metric_id", value=1, type_oid=23, flags={})],
        lsn=lsn,
        commit_timestamp=float(lsn),
    )


@pytest.mark.unit
def test_persistent_store_persists_across_instances(tmp_path):
    store_path = tmp_path / "resume_tokens.json"
    store = PersistentCheckpointStore(store_path)

    store.save("cdc_slot", 12345)
    assert store.load("cdc_slot") == 12345

    persisted = json.loads(store_path.read_text())
    assert persisted == {"cdc_slot": 12345}

    reloaded = PersistentCheckpointStore(store_path)
    assert reloaded.load("cdc_slot") == 12345


@pytest.mark.unit
def test_manual_reset_requires_expected_lsn(tmp_path):
    store = PersistentCheckpointStore(tmp_path / "resume.json")
    slot = "uns_meta_slot"
    store.save(slot, 200)

    with pytest.raises(ValueError):
        store.reset(slot)

    with pytest.raises(ValueError):
        store.reset(slot, expected_lsn=150)

    store.reset(slot, expected_lsn=200)
    assert store.load(slot) is None

    reloaded = PersistentCheckpointStore(tmp_path / "resume.json")
    assert reloaded.load(slot) is None


@pytest.mark.unit
def test_manual_reset_can_override_to_lower_lsn(tmp_path):
    store = PersistentCheckpointStore(tmp_path / "resume.json")
    slot = "uns_meta_slot"
    store.save(slot, 500)

    store.reset(slot, expected_lsn=500, new_lsn=120)
    assert store.load(slot) == 120

    store.save(slot, 130)
    assert store.load(slot) == 130

    contents = json.loads((tmp_path / "resume.json").read_text())
    assert contents == {slot: 130}


@pytest.mark.unit
def test_logical_replication_resumes_after_restart(tmp_path):
    checkpoint_path = tmp_path / "checkpoint.json"
    initial_store = PersistentCheckpointStore(checkpoint_path)

    batches = [
        [
            ReplicationStreamMessage(lsn=100, data=b"{}", commit_timestamp=1.0),
            ReplicationStreamMessage(lsn=110, data=b"{}", commit_timestamp=2.0),
        ],
        [
            ReplicationStreamMessage(lsn=200, data=b"{}", commit_timestamp=3.0),
        ],
    ]
    decoder = _SequentialDecoder(
        [[_build_change(100)], [_build_change(110)], [_build_change(200)]]
    )
    stream = _RecordingStream(batches)

    client = LogicalReplicationClient(
        slot_name="slot",
        stream_factory=stream.factory,
        decoder=decoder,
        checkpoint_store=initial_store,
        checkpoint_interval=1,
    )

    client.process()
    assert initial_store.load("slot") == 110
    assert stream.starts == [None]

    # Re-instantiate store to simulate restart
    resumed_store = PersistentCheckpointStore(checkpoint_path)
    resumed_client = LogicalReplicationClient(
        slot_name="slot",
        stream_factory=stream.factory,
        decoder=_SequentialDecoder([[_build_change(200)]]),
        checkpoint_store=resumed_store,
        checkpoint_interval=1,
    )

    resumed_client.process()
    assert stream.starts == [None, 110]
    assert resumed_store.load("slot") == 200
