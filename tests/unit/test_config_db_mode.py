from pathlib import Path

import pytest

from uns_metadata_sync.config import load_settings


@pytest.fixture(autouse=True)
def _patch_dotenv(monkeypatch):
    monkeypatch.setattr(
        "uns_metadata_sync.config.load_dotenv", lambda *_args, **_kwargs: True
    )


def _seed_minimal_env(monkeypatch, db_mode=None):
    monkeypatch.setenv("MQTT_HOST", "broker")
    monkeypatch.setenv("MQTT_PORT", "1883")
    monkeypatch.setenv("MQTT_USER", "user")
    monkeypatch.setenv("MQTT_PASSWORD", "pass")
    monkeypatch.setenv("MQTT_TOPIC_ALL", "topic/all")
    monkeypatch.setenv("MQTT_TOPIC_NBIRTH_ALL", "topic/nbirth")
    monkeypatch.setenv("MQTT_TOPIC_DBIRTH_ALL", "topic/dbirth")
    monkeypatch.setenv("ALIAS_CACHE_PATH", "aliases.json")
    monkeypatch.setenv("WRITE_JSONL", "false")
    monkeypatch.setenv("JSONL_PATTERN", "pattern")
    monkeypatch.setenv("AUTO_REQUEST_REBIRTH_ON_MISS", "true")
    monkeypatch.setenv("REBIRTH_THROTTLE_SECONDS", "30")
    monkeypatch.setenv("MQTT_CLIENT_ID", "client")
    monkeypatch.setenv("MQTT_TLS_INSECURE", "0")
    monkeypatch.setenv("PGHOST", "localhost")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGDATABASE", "uns_metadata")
    monkeypatch.setenv("PGUSER", "postgres")
    monkeypatch.setenv("PGPASSWORD", "pass")
    monkeypatch.setenv("PGSCHEMA", "uns_meta")
    if db_mode is None:
        monkeypatch.delenv("DB_MODE", raising=False)
    else:
        monkeypatch.setenv("DB_MODE", db_mode)


@pytest.mark.unit
def test_db_mode_default_is_mock(monkeypatch):
    _seed_minimal_env(monkeypatch)
    settings = load_settings()
    assert settings.db_mode == "mock"


@pytest.mark.unit
def test_db_mode_accepts_local(monkeypatch):
    _seed_minimal_env(monkeypatch, db_mode="LOCAL")
    settings = load_settings()
    assert settings.db_mode == "local"


@pytest.mark.unit
def test_db_mode_invalid_value_falls_back_to_mock(monkeypatch):
    _seed_minimal_env(monkeypatch, db_mode="staging")
    settings = load_settings()
    assert settings.db_mode == "mock"


@pytest.mark.unit
def test_db_settings_loaded(monkeypatch):
    _seed_minimal_env(monkeypatch, db_mode="local")
    settings = load_settings()
    assert settings.db_host == "localhost"
    assert settings.db_port == 5432
    assert settings.db_name == "uns_metadata"
    assert settings.db_user == "postgres"
    assert settings.db_password == "pass"
    assert settings.db_schema == "uns_meta"


@pytest.mark.unit
def test_checkpoint_backend_defaults_to_file(monkeypatch):
    _seed_minimal_env(monkeypatch)
    monkeypatch.delenv("CDC_CHECKPOINT_BACKEND", raising=False)
    monkeypatch.delenv("CDC_RESUME_PATH", raising=False)
    monkeypatch.delenv("CDC_RESUME_FSYNC", raising=False)

    settings = load_settings()
    assert settings.cdc_checkpoint_backend == "file"
    assert settings.cdc_resume_path == Path("cdc_resume_tokens.json")
    assert settings.cdc_resume_fsync is False


@pytest.mark.unit
def test_checkpoint_backend_env_overrides(monkeypatch, tmp_path):
    _seed_minimal_env(monkeypatch)
    monkeypatch.setenv("CDC_CHECKPOINT_BACKEND", "MEMORY")
    monkeypatch.setenv("CDC_RESUME_PATH", str(tmp_path / "custom.json"))
    monkeypatch.setenv("CDC_RESUME_FSYNC", "true")

    settings = load_settings()
    assert settings.cdc_checkpoint_backend == "memory"
    assert settings.cdc_resume_path == tmp_path / "custom.json"
    assert settings.cdc_resume_fsync is True
