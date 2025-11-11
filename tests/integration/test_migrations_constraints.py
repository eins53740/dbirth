import os
import time

import pytest

try:
    from uns_metadata_sync.db import connect, errors, sql
except ImportError:  # pragma: no cover - optional dependency
    connect = None
    errors = None

from uns_metadata_sync.migrations.runner import apply_migrations


@pytest.mark.integration
@pytest.mark.skipif(connect is None, reason="psycopg not installed")
def test_schema_constraints_and_triggers():
    if os.getenv("DB_MODE", "mock").lower() != "local":
        pytest.skip("DB_MODE=mock - skipping live Postgres constraint test")

    host = os.getenv("PGHOST", "localhost")
    port = int(os.getenv("PGPORT", "5432"))
    admin_user = os.getenv("PGUSER")
    admin_password = os.getenv("PGPASSWORD")
    owner_password = os.getenv("PGOWNER_PASSWORD", admin_password)

    if not admin_user or admin_password is None:
        pytest.skip("PGUSER/PGPASSWORD must be set for constraint verification")

    temp_db = f"uns_meta_contract_{int(time.time())}"

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
        ) as conn:
            apply_migrations(conn=conn)

        owner_conn = connect(
            host=host,
            port=port,
            user=admin_user,
            password=owner_password,
            dbname=temp_db,
        )
        owner_conn.autocommit = True
        try:
            device_id = owner_conn.execute(
                sql.SQL(
                    """
                    INSERT INTO uns_meta.devices (
                        group_id, country, business_unit, plant, edge, device, uns_path
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING device_id, created_at, updated_at
                    """
                ),
                (
                    "SECIL.GROUP",
                    "PT",
                    "Cement",
                    "OUT",
                    "EDGE-01",
                    "DEVICE-01",
                    "spBv1.0/Secil/DBIRTH/EDGE-01/DEVICE-01",
                ),
            ).fetchone()
            device_id, created_at, updated_at = device_id

            time.sleep(0.01)
            refreshed = owner_conn.execute(
                "UPDATE uns_meta.devices SET business_unit = %s WHERE device_id = %s RETURNING updated_at",
                ("Cement-Updated", device_id),
            ).fetchone()
            assert refreshed[0] > updated_at

            metric_id = owner_conn.execute(
                sql.SQL(
                    """
                    INSERT INTO uns_meta.metrics (
                        device_id, name, uns_path, datatype
                    ) VALUES (%s, %s, %s, %s)
                    RETURNING metric_id
                    """
                ),
                (
                    device_id,
                    "temp",
                    "spBv1.0/Secil/DDATA/EDGE-01/DEVICE-01/temp",
                    "float",
                ),
            ).fetchone()[0]

            owner_conn.execute(
                sql.SQL(
                    """
                    INSERT INTO uns_meta.metric_properties (
                        metric_id, key, type, value_string
                    ) VALUES (%s, %s, %s, %s)
                    """
                ),
                (metric_id, "engineering_unit", "string", "C"),
            )

            with pytest.raises(errors.CheckViolation):
                owner_conn.execute(
                    sql.SQL(
                        """
                        INSERT INTO uns_meta.metric_properties (
                            metric_id, key, type, value_int, value_string
                        ) VALUES (%s, %s, %s, %s, %s)
                        """
                    ),
                    (metric_id, "invalid", "boolean", 1, "true"),
                )

            trigger_updated_at = owner_conn.execute(
                "SELECT count(*) FROM pg_trigger WHERE tgname = %s",
                ("trg_metric_properties_updated_at",),
            ).fetchone()[0]
            assert trigger_updated_at == 1
        finally:
            owner_conn.close()
    finally:
        with connect(
            host=host,
            port=port,
            user=admin_user,
            password=admin_password,
            dbname="postgres",
        ) as cleanup:
            cleanup.autocommit = True
            cleanup.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (temp_db,),
            )
            cleanup.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(temp_db))
            )
