"""Utilities for CDC logical replication, debouncing, and diff aggregation."""

from .checkpoint import InMemoryCheckpointStore, PersistentCheckpointStore
from .logical_replication import (
    ChangeColumn,
    ChangeRecord,
    LogicalReplicationClient,
    ReplicationStreamMessage,
    ExponentialBackoff,
    BackoffExhausted,
)
from .debounce import DebounceBuffer, DebounceMetrics
from .diffing import DiffAccumulator, DiffEvent
from .service import (
    CDCListenerMetrics,
    CDCListenerService,
    JsonChangeDecoder,
    MetricIdentity,
    MetricMetadataProvider,
    MetricVersionSnapshot,
    PostgresMetadataProvider,
    build_cdc_listener,
    create_pgoutput_stream_factory,
    int_to_lsn,
)

__all__ = [
    "BackoffExhausted",
    "ChangeColumn",
    "ChangeRecord",
    "CDCListenerMetrics",
    "CDCListenerService",
    "DebounceBuffer",
    "DebounceMetrics",
    "DiffAccumulator",
    "DiffEvent",
    "ExponentialBackoff",
    "InMemoryCheckpointStore",
    "JsonChangeDecoder",
    "LogicalReplicationClient",
    "MetricIdentity",
    "MetricMetadataProvider",
    "MetricVersionSnapshot",
    "PersistentCheckpointStore",
    "PostgresMetadataProvider",
    "ReplicationStreamMessage",
    "build_cdc_listener",
    "create_pgoutput_stream_factory",
    "int_to_lsn",
]
