from pathlib import Path
from typing import Iterable, Optional

import pytest

from uns_metadata_sync.cdc.checkpoint import (
    InMemoryCheckpointStore,
    PersistentCheckpointStore,
)
from uns_metadata_sync.cdc.logical_replication import (
    ChangeRecord,
    ReplicationStreamMessage,
)
from uns_metadata_sync.cdc.service import build_cdc_listener
from uns_metadata_sync.config import Settings


class _StaticDecoder:
    def decode(self, _message: ReplicationStreamMessage) -> Iterable[ChangeRecord]:
        return []


class _NullMetadataProvider:
    def get_identity(self, _metric_id: int):
        return None

    def get_version_snapshot(self, _metric_id: int):
        return None


def _base_settings(tmp_path: Path, **overrides) -> Settings:
    base = {
        "broker": "broker",
        "port": 1883,
        "username": "user",
        "password": "pass",
        "topic_all": "topic/all",
        "topic_nbirth_all": "topic/nbirth",
        "topic_dbirth_all": "topic/dbirth",
        "alias_cache_path": tmp_path / "alias_cache.json",
        "write_jsonl": False,
        "jsonl_pattern": str(tmp_path / "messages_{topic}.jsonl"),
        "auto_request_rebirth": True,
        "rebirth_throttle_seconds": 30,
        "client_id": "client",
        "tls_insecure": False,
        "db_mode": "local",
        "db_host": "localhost",
        "db_port": 5432,
        "db_name": "uns_metadata",
        "db_user": "postgres",
        "db_password": "pass",
        "db_schema": "uns_meta",
        "cdc_enabled": True,
        "cdc_slot": "uns_meta_slot",
        "cdc_publication": "uns_meta_pub",
        "cdc_window_seconds": 180,
        "cdc_flush_interval_seconds": 5.0,
        "cdc_buffer_cap": 1000,
        "cdc_idle_sleep_seconds": 1.0,
        "cdc_max_batch_messages": 500,
        "pg_replication_user": "postgres",
        "pg_replication_password": "pass",
        "pg_replication_host": "localhost",
        "pg_replication_port": 5432,
        "pg_replication_database": "uns_metadata",
        "pg_replication_sslmode": "prefer",
        "cdc_checkpoint_backend": "file",
        "cdc_resume_path": tmp_path / "resume_tokens.json",
        "cdc_resume_fsync": False,
    }
    base.update(overrides)
    return Settings(**base)


def _empty_stream(_lsn: Optional[int]):
    return iter([])  # type: ignore[return-value]


@pytest.mark.unit
def test_build_listener_uses_persistent_store(tmp_path):
    settings = _base_settings(tmp_path)
    listener = build_cdc_listener(
        settings,
        diff_sink=lambda payload: None,
        stream_factory=_empty_stream,
        decoder=_StaticDecoder(),
        metadata_provider=_NullMetadataProvider(),
    )

    assert isinstance(listener._checkpoint_store, PersistentCheckpointStore)
    assert listener._checkpoint_store.load(settings.cdc_slot) is None
    assert listener._client.slot_name == settings.cdc_slot


@pytest.mark.unit
def test_build_listener_uses_memory_store_when_configured(tmp_path):
    settings = _base_settings(tmp_path, cdc_checkpoint_backend="memory")
    listener = build_cdc_listener(
        settings,
        diff_sink=lambda payload: None,
        stream_factory=_empty_stream,
        decoder=_StaticDecoder(),
        metadata_provider=_NullMetadataProvider(),
    )

    assert isinstance(listener._checkpoint_store, InMemoryCheckpointStore)
