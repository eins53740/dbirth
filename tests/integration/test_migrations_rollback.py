import os
import uuid

import pytest

try:
    from uns_metadata_sync.db import connect, sql
except ImportError:  # pragma: no cover - psycopg not available when dev extras missing.
    connect = None

from uns_metadata_sync.migrations.runner import apply_migrations, rollback_last


@pytest.mark.integration
def test_migration_rollback_cycle():
    if os.getenv("DB_MODE", "mock").lower() != "local":
        pytest.skip("DB_MODE=mock – skipping live Postgres rollback test")

    if connect is None:
        pytest.skip("psycopg not installed for integration test")

    host = os.getenv("PGHOST", "localhost")
    port = int(os.getenv("PGPORT", "5432"))
    admin_user = os.getenv("PGUSER")
    admin_password = os.getenv("PGPASSWORD")

    if not admin_user or admin_password is None:
        pytest.skip("PGUSER/PGPASSWORD must be set for rollback verification")

    temp_db = f"uns_meta_test_{uuid.uuid4().hex[:8]}"

    admin_conn = connect(
        host=host,
        port=port,
        user=admin_user,
        password=admin_password,
        dbname="postgres",
    )
    admin_conn.autocommit = True
    try:
        admin_conn.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(temp_db), sql.Identifier(admin_user)
            )
        )
    finally:
        admin_conn.close()

    try:
        with connect(
            host=host,
            port=port,
            user=admin_user,
            password=admin_password,
            dbname=temp_db,
        ) as apply_conn:
            applied = apply_migrations(conn=apply_conn)
            assert [migration.version for migration in applied] == ["000", "001"]

        with connect(
            host=host,
            port=port,
            user=admin_user,
            password=admin_password,
            dbname=temp_db,
        ) as db:
            devices_regclass = db.execute(
                "SELECT to_regclass('uns_meta.devices')"
            ).fetchone()[0]
            assert devices_regclass is not None

            rolled_back = rollback_last(conn=db)
            assert rolled_back is not None
            assert rolled_back.version == "001"

            devices_after_rollback = db.execute(
                "SELECT to_regclass('uns_meta.devices')"
            ).fetchone()[0]
            assert devices_after_rollback is None

            reapplied = apply_migrations(conn=db)
            assert reapplied and reapplied[-1].version == "001"
    finally:
        with connect(
            host=host,
            port=port,
            user=admin_user,
            password=admin_password,
            dbname="postgres",
        ) as admin_cleanup:
            admin_cleanup.autocommit = True
            admin_cleanup.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (temp_db,),
            )
            admin_cleanup.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(temp_db))
            )
