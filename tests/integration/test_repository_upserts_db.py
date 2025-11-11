import os
import uuid

import pytest

try:
    from uns_metadata_sync.db import connect
except ImportError:  # pragma: no cover - optional dependency
    connect = None

from uns_metadata_sync.db.repository import (
    DevicePayload,
    MetadataRepository,
    MetricPayload,
    MetricPropertyPayload,
    RepositoryError,
)
from uns_metadata_sync.migrations.runner import apply_migrations


pytestmark = pytest.mark.integration


@pytest.fixture()
def temp_db():
    if connect is None:
        pytest.skip("psycopg not installed")

    host = os.getenv("PGHOST", "localhost")
    port = int(os.getenv("PGPORT", "5432"))
    admin_user = os.getenv("PGUSER", "postgres")
    admin_password = os.getenv("PGPASSWORD", "postgres")

    temp_db_name = f"uns_meta_repo_{uuid.uuid4().hex[:8]}"

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
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (temp_db_name,),
        )
        admin_conn.execute(f"CREATE DATABASE {temp_db_name} OWNER {admin_user}")
    finally:
        admin_conn.close()

    try:
        with connect(
            host=host,
            port=port,
            user=admin_user,
            password=admin_password,
            dbname=temp_db_name,
        ) as conn:
            apply_migrations(conn=conn)

        yield {
            "host": host,
            "port": port,
            "user": admin_user,
            "password": admin_password,
            "dbname": temp_db_name,
        }
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
                (temp_db_name,),
            )
            cleanup.execute(f"DROP DATABASE IF EXISTS {temp_db_name}")


@pytest.fixture()
def repository(temp_db):
    conn = connect(**temp_db)
    repo = MetadataRepository(conn)
    try:
        yield repo
    finally:
        conn.close()


def _device_payload(**overrides):
    data = {
        "group_id": "SECIL.GROUP",
        "country": "PT",
        "business_unit": "Cement",
        "plant": "OUT",
        "edge": "EDGE-01",
        "device": "DEVICE-01",
        "uns_path": "SECIL.GROUP/EDGE-01/DEVICE-01",
    }
    data.update(overrides)
    return DevicePayload(**data)


def test_device_upsert_insert_update_noop(repository):
    payload = _device_payload()

    inserted = repository.upsert_device(payload)
    assert inserted.status == "inserted"
    inserted_row = inserted.record

    noop = repository.upsert_device(payload)
    assert noop.status == "noop"
    assert noop.record["device_id"] == inserted_row["device_id"]
    assert noop.record["updated_at"] == inserted_row["updated_at"]

    updated_payload = _device_payload(business_unit="Aggregates")
    updated = repository.upsert_device(updated_payload)
    assert updated.status == "updated"
    assert updated.record["device_id"] == inserted_row["device_id"]
    assert updated.record["updated_at"] > inserted_row["updated_at"]


def test_device_upsert_handles_not_null_violation(repository):
    with pytest.raises(RepositoryError) as excinfo:
        repository.upsert_device(
            _device_payload(
                group_id=None,
                uns_path="SECIL.GROUP/EDGE-01/DEVICE-ERR",
            )  # type: ignore[arg-type]
        )
    assert "device upsert failed" in str(excinfo.value)


def test_metric_and_property_upserts(repository):
    device = repository.upsert_device(_device_payload())
    device_id = device.record["device_id"]

    metric_payload = MetricPayload(
        device_id=device_id,
        name="temperature",
        uns_path="SECIL.GROUP/EDGE-01/DEVICE-01/temperature",
        datatype="double",
    )

    metric_insert = repository.upsert_metric(metric_payload)
    assert metric_insert.status == "inserted"
    metric_id = metric_insert.record["metric_id"]

    metric_update = repository.upsert_metric(
        MetricPayload(
            device_id=device_id,
            name="temperature",
            uns_path="SECIL.GROUP/EDGE-01/DEVICE-01/temperature",
            datatype="string",
        )
    )
    assert metric_update.status == "updated"
    assert metric_update.record["datatype"] == "string"

    property_payload = MetricPropertyPayload(
        metric_id=metric_id,
        key="engineering_unit",
        type="string",
        value="C",
    )

    prop_insert = repository.upsert_metric_property(property_payload)
    assert prop_insert.status == "inserted"

    prop_update = repository.upsert_metric_property(
        MetricPropertyPayload(
            metric_id=metric_id,
            key="engineering_unit",
            type="string",
            value="F",
        )
    )
    assert prop_update.status == "updated"
    assert prop_update.record["value_string"] == "F"

    prop_noop = repository.upsert_metric_property(
        MetricPropertyPayload(
            metric_id=metric_id,
            key="engineering_unit",
            type="string",
            value="F",
        )
    )
    assert prop_noop.status == "noop"
