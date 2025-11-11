"""Runtime configuration helpers for the UNS metadata sync service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Immutable container for service configuration."""

    broker: str
    port: int
    username: str
    password: str
    topic_all: str
    topic_nbirth_all: str
    topic_dbirth_all: str
    alias_cache_path: Path
    write_jsonl: bool
    jsonl_pattern: str
    auto_request_rebirth: bool
    rebirth_throttle_seconds: int
    client_id: str
    tls_insecure: bool
    db_mode: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_schema: str
    cdc_enabled: bool
    cdc_slot: str
    cdc_publication: str
    cdc_window_seconds: int
    cdc_flush_interval_seconds: float
    cdc_buffer_cap: int
    cdc_idle_sleep_seconds: float
    cdc_max_batch_messages: int
    cdc_checkpoint_backend: str
    cdc_resume_path: Path
    cdc_resume_fsync: bool
    pg_replication_user: str
    pg_replication_password: str
    pg_replication_host: str
    pg_replication_port: int
    pg_replication_database: str
    pg_replication_sslmode: str
    canary_enabled: bool = False
    canary_base_url: str = ""
    canary_api_token: str = ""
    canary_client_id: str = ""
    canary_historians: Tuple[str, ...] = ()
    canary_rate_limit_rps: int = 500
    canary_queue_capacity: int = 1000
    canary_max_batch_tags: int = 100
    canary_max_payload_bytes: int = 1_000_000
    canary_request_timeout_seconds: float = 10.0
    canary_retry_attempts: int = 6
    canary_retry_base_delay_seconds: float = 0.2
    canary_retry_max_delay_seconds: float = 6.4
    canary_circuit_consecutive_failures: int = 20
    canary_circuit_reset_seconds: float = 60.0
    canary_session_timeout_ms: int = 120000
    canary_keepalive_idle_seconds: int = 30
    canary_keepalive_jitter_seconds: int = 10
    cdc_replication_plugin: str = "wal2json"


def _as_bool(value: Optional[str], default: bool) -> bool:
    """Convert environment strings to booleans."""
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no"}


def _coerce_db_mode(value: Optional[str]) -> str:
    """Translate DB_MODE env var to a supported value."""
    if value is None:
        return "mock"
    normalized = value.strip().lower()
    if normalized in {"mock", "local"}:
        return normalized
    return "mock"


def _coerce_checkpoint_backend(value: Optional[str]) -> str:
    if value is None:
        return "file"
    normalized = value.strip().lower()
    if normalized in {"memory", "file"}:
        return normalized
    return "file"


def _split_csv(value: Optional[str]) -> Tuple[str, ...]:
    if not value:
        return ()
    return tuple(entry.strip() for entry in value.split(",") if entry.strip())


def load_settings() -> Settings:
    """Load configuration from the environment (and `.env`)."""
    load_dotenv()
    broker = os.getenv("MQTT_HOST", "")
    port = int(os.getenv("MQTT_PORT", "1883"))
    username = os.getenv("MQTT_USER", "")
    password = os.getenv("MQTT_PASSWORD", "")

    topic_all = os.getenv("MQTT_TOPIC_ALL", "spBv1.0/Secil/DBIRTH/#")
    topic_nbirth_all = os.getenv("MQTT_TOPIC_NBIRTH_ALL", "spBv1.0/+/NBIRTH/#")
    topic_dbirth_all = os.getenv("MQTT_TOPIC_DBIRTH_ALL", "spBv1.0/+/DBIRTH/#")

    alias_cache_path = Path(os.getenv("ALIAS_CACHE_PATH", "alias_cache.json"))
    write_jsonl = _as_bool(os.getenv("WRITE_JSONL"), True)
    jsonl_pattern = os.getenv("JSONL_PATTERN", "messages_{topic}.jsonl")

    auto_request_rebirth = _as_bool(os.getenv("AUTO_REQUEST_REBIRTH_ON_MISS"), True)
    rebirth_throttle_seconds = int(os.getenv("REBIRTH_THROTTLE_SECONDS", "60"))

    client_id = os.getenv("MQTT_CLIENT_ID", "spb_sub_microservice")
    tls_insecure = _as_bool(os.getenv("MQTT_TLS_INSECURE"), True)
    db_mode = _coerce_db_mode(os.getenv("DB_MODE"))
    db_host = os.getenv("PGHOST", "localhost")
    db_port = int(os.getenv("PGPORT", "5432"))
    db_name = os.getenv("PGDATABASE", "uns_metadata")
    db_user = os.getenv("PGUSER", "postgres")
    db_password = os.getenv("PGPASSWORD", "")
    db_schema = os.getenv("PGSCHEMA", "uns_meta")
    cdc_enabled = _as_bool(os.getenv("CDC_ENABLED"), True)
    cdc_slot = os.getenv("PGREPL_SLOT", "uns_meta_slot")
    cdc_publication = os.getenv("PGREPL_PUBLICATION", "uns_meta_pub")
    cdc_window_seconds = int(os.getenv("CDC_DEBOUNCE_SECONDS", "180"))
    cdc_flush_interval_seconds = float(os.getenv("CDC_FLUSH_INTERVAL_SECONDS", "5"))
    cdc_buffer_cap = int(os.getenv("CDC_BUFFER_CAP", "1000"))
    cdc_idle_sleep_seconds = float(os.getenv("CDC_IDLE_SLEEP_SECONDS", "1"))
    cdc_max_batch_messages = int(os.getenv("CDC_MAX_BATCH_MESSAGES", "500"))
    cdc_checkpoint_backend = _coerce_checkpoint_backend(
        os.getenv("CDC_CHECKPOINT_BACKEND")
    )
    cdc_resume_path = Path(os.getenv("CDC_RESUME_PATH", "cdc_resume_tokens.json"))
    cdc_resume_fsync = _as_bool(os.getenv("CDC_RESUME_FSYNC"), False)
    cdc_replication_plugin = os.getenv("CDC_REPLICATION_PLUGIN", "wal2json").strip()
    pg_replication_user = os.getenv("PGREPLUSER", db_user)
    pg_replication_password = os.getenv("PGREPLPASSWORD", db_password)
    pg_replication_host = os.getenv("PGREPLHOST", db_host)
    pg_replication_port = int(os.getenv("PGREPLPORT", str(db_port)))
    pg_replication_database = os.getenv("PGREPLDATABASE", db_name)
    pg_replication_sslmode = os.getenv(
        "PGREPLSSLMODE", os.getenv("PGSSLMODE", "prefer")
    )

    canary_base_url = os.getenv("CANARY_SAF_BASE_URL", "").strip()
    canary_api_token = os.getenv("CANARY_API_TOKEN", "").strip()
    canary_client_id = os.getenv("CANARY_CLIENT_ID", "").strip()
    canary_historians = _split_csv(os.getenv("CANARY_HISTORIANS"))
    canary_enabled = _as_bool(
        os.getenv("CANARY_WRITER_ENABLED"),
        bool(canary_base_url and canary_api_token),
    )
    canary_rate_limit_rps = int(os.getenv("CANARY_RATE_LIMIT_RPS", "500"))
    canary_queue_capacity = int(os.getenv("CANARY_QUEUE_CAPACITY", "1000"))
    canary_max_batch_tags = int(os.getenv("CANARY_MAX_BATCH_TAGS", "100"))
    canary_max_payload_bytes = int(os.getenv("CANARY_MAX_PAYLOAD_BYTES", "1000000"))
    canary_request_timeout_seconds = float(
        os.getenv("CANARY_REQUEST_TIMEOUT_SECONDS", "10.0")
    )
    canary_retry_attempts = int(os.getenv("CANARY_RETRY_ATTEMPTS", "6"))
    canary_retry_base_delay_seconds = float(
        os.getenv("CANARY_RETRY_BASE_DELAY_SECONDS", "0.2")
    )
    canary_retry_max_delay_seconds = float(
        os.getenv("CANARY_RETRY_MAX_DELAY_SECONDS", "6.4")
    )
    canary_circuit_consecutive_failures = int(
        os.getenv("CANARY_CIRCUIT_CONSECUTIVE_FAILURES", "20")
    )
    canary_circuit_reset_seconds = float(
        os.getenv("CANARY_CIRCUIT_RESET_SECONDS", "60.0")
    )
    canary_session_timeout_ms = int(os.getenv("CANARY_SESSION_TIMEOUT_MS", "120000"))
    canary_keepalive_idle_seconds = int(
        os.getenv("CANARY_KEEPALIVE_IDLE_SECONDS", "30")
    )
    canary_keepalive_jitter_seconds = int(
        os.getenv("CANARY_KEEPALIVE_JITTER_SECONDS", "10")
    )

    if canary_base_url.endswith("/"):
        canary_base_url = canary_base_url.rstrip("/")

    return Settings(
        broker=broker,
        port=port,
        username=username,
        password=password,
        topic_all=topic_all,
        topic_nbirth_all=topic_nbirth_all,
        topic_dbirth_all=topic_dbirth_all,
        alias_cache_path=alias_cache_path,
        write_jsonl=write_jsonl,
        jsonl_pattern=jsonl_pattern,
        auto_request_rebirth=auto_request_rebirth,
        rebirth_throttle_seconds=rebirth_throttle_seconds,
        client_id=client_id,
        tls_insecure=tls_insecure,
        db_mode=db_mode,
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_user=db_user,
        db_password=db_password,
        db_schema=db_schema,
        cdc_enabled=cdc_enabled,
        cdc_slot=cdc_slot,
        cdc_publication=cdc_publication,
        cdc_window_seconds=cdc_window_seconds,
        cdc_flush_interval_seconds=cdc_flush_interval_seconds,
        cdc_buffer_cap=cdc_buffer_cap,
        cdc_idle_sleep_seconds=cdc_idle_sleep_seconds,
        cdc_max_batch_messages=cdc_max_batch_messages,
        cdc_checkpoint_backend=cdc_checkpoint_backend,
        cdc_resume_path=cdc_resume_path,
        cdc_resume_fsync=cdc_resume_fsync,
        cdc_replication_plugin=cdc_replication_plugin or "wal2json",
        pg_replication_user=pg_replication_user,
        pg_replication_password=pg_replication_password,
        pg_replication_host=pg_replication_host,
        pg_replication_port=pg_replication_port,
        pg_replication_database=pg_replication_database,
        pg_replication_sslmode=pg_replication_sslmode,
        canary_enabled=canary_enabled,
        canary_base_url=canary_base_url,
        canary_api_token=canary_api_token,
        canary_client_id=canary_client_id,
        canary_historians=canary_historians,
        canary_rate_limit_rps=canary_rate_limit_rps,
        canary_queue_capacity=canary_queue_capacity,
        canary_max_batch_tags=canary_max_batch_tags,
        canary_max_payload_bytes=canary_max_payload_bytes,
        canary_request_timeout_seconds=canary_request_timeout_seconds,
        canary_retry_attempts=canary_retry_attempts,
        canary_retry_base_delay_seconds=canary_retry_base_delay_seconds,
        canary_retry_max_delay_seconds=canary_retry_max_delay_seconds,
        canary_circuit_consecutive_failures=canary_circuit_consecutive_failures,
        canary_circuit_reset_seconds=canary_circuit_reset_seconds,
        canary_session_timeout_ms=canary_session_timeout_ms,
        canary_keepalive_idle_seconds=canary_keepalive_idle_seconds,
        canary_keepalive_jitter_seconds=canary_keepalive_jitter_seconds,
    )
