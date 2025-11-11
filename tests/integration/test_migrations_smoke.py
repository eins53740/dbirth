import os

import pytest

from uns_metadata_sync.db import OperationalError, connect
from uns_metadata_sync.migrations.runner import apply_migrations


@pytest.mark.integration
def test_migrations_smoke_against_local_postgres():
    if os.getenv("DB_MODE", "mock").lower() != "local":
        pytest.skip("DB_MODE=mock – skipping live Postgres smoke test")

    try:
        with connect() as connection:
            apply_migrations(conn=connection, dry_run=True)
    except OperationalError as exc:  # pragma: no cover - depends on env
        pytest.skip(f"Postgres unavailable: {exc}")
