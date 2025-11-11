import pytest

from uns_metadata_sync.cdc.logical_replication import (
    ChangeColumn,
    ChangeRecord,
    LogicalReplicationClient,
    ReplicationStreamMessage,
    ExponentialBackoff,
    BackoffExhausted,
)


class DictCheckpointStore:
    def __init__(self) -> None:
        self.state: dict[str, int] = {}
        self.saves: list[int] = []

    def load(self, slot_name: str) -> int | None:
        return self.state.get(slot_name)

    def save(self, slot_name: str, lsn: int) -> None:
        self.state[slot_name] = lsn
        self.saves.append(lsn)

    def reset(
        self,
        slot_name: str,
        *,
        expected_lsn: int | None = None,
        new_lsn: int | None = None,
        force: bool = False,
    ) -> None:
        current = self.state.get(slot_name)
        if current is None and new_lsn is None:
            return
        if not force and current is not None and expected_lsn != current:
            raise ValueError("unexpected LSN")
        if new_lsn is None:
            self.state.pop(slot_name, None)
        else:
            self.state[slot_name] = new_lsn


class DummyDecoder:
    def __init__(self, messages: list[list[ChangeRecord]]) -> None:
        self._messages = messages
        self._index = 0

    def decode(self, message: ReplicationStreamMessage):
        decoded = self._messages[self._index]
        self._index += 1
        return decoded


class FaultyIterable:
    def __iter__(self):
        raise RuntimeError("stream failure")


def build_change(
    lsn: int,
    relation: str,
    payload: dict[str, tuple[object, int, dict[str, bool]]],
    kind: str = "insert",
):
    columns = [
        ChangeColumn(name=name, value=value, type_oid=oid, flags=flags)
        for name, (value, oid, flags) in payload.items()
    ]
    return ChangeRecord(
        kind=kind,
        relation=relation,
        columns=columns,
        lsn=lsn,
        commit_timestamp=1234.5,
    )


@pytest.mark.unit
def test_logical_replication_decodes_relation_and_columns():
    changes = [
        [
            build_change(
                100, "metrics", {"metric_id": (10, 23, {}), "name": ("temp", 25, {})}
            )
        ],
        [
            build_change(
                110,
                "metric_properties",
                {
                    "metric_id": (10, 23, {}),
                    "key": ("engUnit", 25, {"key": True}),
                    "value_string": ("C", 25, {}),
                },
                kind="update",
            )
        ],
    ]
    decoder = DummyDecoder(changes)
    messages = [
        ReplicationStreamMessage(lsn=100, data=b"", commit_timestamp=1.0),
        ReplicationStreamMessage(lsn=110, data=b"", commit_timestamp=2.0),
    ]
    captured: list[ChangeRecord] = []

    def stream_factory(start_lsn):
        assert start_lsn is None
        return iter(messages)

    client = LogicalReplicationClient(
        slot_name="test_slot",
        stream_factory=stream_factory,
        decoder=decoder,
        checkpoint_store=DictCheckpointStore(),
        handler=captured.append,
        checkpoint_interval=1,
    )

    processed = client.process()

    assert processed == 2
    assert len(captured) == 2
    first = captured[0]
    assert first.relation == "metrics"
    assert [col.name for col in first.columns] == ["metric_id", "name"]
    assert first.columns[0].value == 10
    assert first.columns[1].value == "temp"
    second = captured[1]
    assert second.kind == "update"
    assert second.columns[1].flags == {"key": True}
    assert second.columns[2].value == "C"


@pytest.mark.unit
def test_checkpoint_persisted_across_reconnect():
    store = DictCheckpointStore()
    batches = [
        [
            ReplicationStreamMessage(lsn=100, data=b"a", commit_timestamp=1.0),
            ReplicationStreamMessage(lsn=110, data=b"b", commit_timestamp=2.0),
        ],
        [
            ReplicationStreamMessage(lsn=200, data=b"c", commit_timestamp=3.0),
        ],
    ]
    decoder = DummyDecoder(
        [
            [
                build_change(
                    100, "metrics", {"metric_id": (1, 23, {}), "name": ("temp", 25, {})}
                )
            ],
            [
                build_change(
                    110, "metrics", {"metric_id": (1, 23, {}), "name": ("temp", 25, {})}
                )
            ],
            [
                build_change(
                    200, "metrics", {"metric_id": (2, 23, {}), "name": ("rpm", 25, {})}
                )
            ],
        ]
    )
    starts: list[int | None] = []

    def stream_factory(start_lsn):
        starts.append(start_lsn)
        return iter(batches.pop(0))

    client = LogicalReplicationClient(
        slot_name="test_slot",
        stream_factory=stream_factory,
        decoder=decoder,
        checkpoint_store=store,
        checkpoint_interval=1,
    )

    client.process()
    assert store.state["test_slot"] == 110
    assert starts == [None]

    client.process()
    assert store.state["test_slot"] == 200
    assert starts == [None, 110]
    assert store.saves[-1] == 200


@pytest.mark.unit
def test_backoff_schedule_and_reset():
    store = DictCheckpointStore()
    backoff = ExponentialBackoff(
        base_interval=0.5,
        multiplier=2.0,
        max_interval=6.4,
        max_attempts=6,
        jitter=False,
    )
    iterables = [FaultyIterable(), []]

    def stream_factory(start_lsn):
        return iterables.pop(0)

    decoder = DummyDecoder([])
    client = LogicalReplicationClient(
        slot_name="slot",
        stream_factory=stream_factory,
        decoder=decoder,
        checkpoint_store=store,
        backoff=backoff,
    )

    with pytest.raises(RuntimeError):
        client.process()
    assert client.last_error_delay == 0.5
    assert backoff.attempts == 1

    delays = [0.5, 1.0, 2.0, 4.0, 6.4, 6.4]
    backoff.reset()
    generated = [backoff.next_delay() for _ in range(6)]
    assert generated == delays

    success_client = LogicalReplicationClient(
        slot_name="slot",
        stream_factory=lambda start_lsn: iter([]),
        decoder=DummyDecoder([]),
        checkpoint_store=store,
        backoff=backoff,
    )
    processed = success_client.process()
    assert processed == 0
    assert success_client.last_error_delay is None
    assert backoff.attempts == 0

    with pytest.raises(BackoffExhausted):
        for _ in range(7):
            backoff.next_delay()
