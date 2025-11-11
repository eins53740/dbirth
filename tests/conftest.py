"""Test session configuration.

This module auto-loads environment variables from the project `.env` file so
integration tests can read `DB_MODE` and `PG*` settings without requiring the
developer to export them manually in the shell.
"""

from __future__ import annotations

import pytest


try:  # Optional dev dependency in this project
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - fallback when dotenv is missing

    def load_dotenv(*_args, **_kwargs):  # type: ignore[no-redef]
        return False


@pytest.fixture(scope="session", autouse=True)
def _load_dotenv_for_tests() -> None:
    # Load once per test session; no error if .env is absent.
    load_dotenv()


# Note: Individual tests can use the `monkeypatch` fixture to override env vars.
