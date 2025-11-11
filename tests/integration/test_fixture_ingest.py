import json
import os
import uuid
from pathlib import Path

import pytest

try:
    from uns_metadata_sync.db import connect, sql
except ImportError:  # pragma: no cover - optional dependency
    connect = None
    sql = None

from uns_metadata_sync.db.repository import (
    DevicePayload,
    MetadataRepository,
    MetricPayload,
    MetricPropertyPayload,
)
from uns_metadata_sync.migrations.runner import apply_migrations
from uns_metadata_sync.path_normalizer import (
    normalize_device_path,
    normalize_metric_path,
)


pytestmark = pytest.mark.integration

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json"
)


def _value_type_to_db_type(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int" if -2147483648 <= value <= 2147483647 else "long"
    if isinstance(value, float):
        return "double"
    return "string"


def _extract_metric_value(metric_entry):
    for field in (
        "booleanValue",
        "intValue",
        "longValue",
        "floatValue",
        "doubleValue",
        "stringValue",
    ):
        if field in metric_entry:
            return metric_entry[field]
    return None


def _props_array_to_dict(props):
    result = {}
    if not props or "keys" not in props or "values" not in props:
        return result
    keys = props.get("keys") or []
    values = props.get("values") or []
    for key, value_entry in zip(keys, values):
        for field in (
            "stringValue",
            "booleanValue",
            "intValue",
            "longValue",
            "floatValue",
            "doubleValue",
        ):
            if field in value_entry:
                result[str(key)] = value_entry[field]
                break
    return result


def _scalar_from_cursor(cursor):
    row = cursor.fetchone()
    if not row:
        return 0
    if hasattr(row, "values"):
        return next(iter(row.values()))
    return row[0]


@pytest.mark.skipif(connect is None, reason="psycopg not installed")
def test_fixture_ingest_populates_database():
    host = os.getenv("PGHOST", "localhost")
    port = int(os.getenv("PGPORT", "5432"))
    admin_user = os.getenv("PGUSER")
    admin_password = os.getenv("PGPASSWORD")

    if not admin_user or admin_password is None:
        pytest.skip("PGUSER/PGPASSWORD must be set for integration test")

    temp_db = f"uns_meta_fixture_{uuid.uuid4().hex[:8]}"

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
            (temp_db,),
        )
        admin_conn.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(temp_db),
                sql.Identifier(admin_user),
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
            conn.execute("SET search_path TO uns_meta, public")

            repo = MetadataRepository(conn)
            fixture_data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

            group = "Secil"
            edge = "Maceira-Ignition-Edge"
            device = "Kiln-K1"

            device_payload = DevicePayload(
                group_id=group,
                country="PT",
                business_unit="Cement",
                plant="OUT",
                edge=edge,
                device=device,
                uns_path=normalize_device_path(
                    group=group, edge_node=edge, device=device
                ),
            )

            dev_result = repo.upsert_device(device_payload)
            device_id = dev_result.record["device_id"]

            metrics = fixture_data.get("metrics", [])
            total_properties = 0

            for metric_entry in metrics:
                metric_name = metric_entry.get("name")
                if not metric_name:
                    continue
                value = _extract_metric_value(metric_entry)
                datatype = metric_entry.get("datatype")
                datatype_name = (
                    datatype
                    if isinstance(datatype, str) and datatype
                    else _value_type_to_db_type(value)
                )
                metric_result = repo.upsert_metric(
                    MetricPayload(
                        device_id=device_id,
                        name=metric_name,
                        uns_path=normalize_metric_path(
                            group=group,
                            edge_node=edge,
                            device=device,
                            metric_name=metric_name,
                        ),
                        datatype=str(datatype_name),
                    )
                )
                metric_id = metric_result.record["metric_id"]

                props = _props_array_to_dict(metric_entry.get("properties"))
                for key, prop_value in props.items():
                    repo.upsert_metric_property(
                        MetricPropertyPayload(
                            metric_id=metric_id,
                            key=key,
                            type=_value_type_to_db_type(prop_value),
                            value=prop_value,
                        )
                    )
                    total_properties += 1

            cursor = conn.execute("SELECT COUNT(*) FROM uns_meta.devices")
            device_count = _scalar_from_cursor(cursor)
            cursor = conn.execute("SELECT COUNT(*) FROM uns_meta.metrics")
            metric_count = _scalar_from_cursor(cursor)
            cursor = conn.execute("SELECT COUNT(*) FROM uns_meta.metric_properties")
            property_count = _scalar_from_cursor(cursor)

            assert device_count == 1
            assert metric_count == len(metrics)
            assert property_count == total_properties

            # spot check a property value
            cursor = conn.execute(
                """
                SELECT value_string
                  FROM uns_meta.metric_properties
                 WHERE key = 'DataPermission'
                LIMIT 1
                """
            )
            sample = cursor.fetchone()
            assert sample is not None
            value_string = (
                sample["value_string"]
                if hasattr(sample, "__getitem__") and "value_string" in sample
                else sample[0]
            )
            assert "G_UNS_Admin" in value_string
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
