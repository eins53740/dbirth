from __future__ import annotations

import argparse
import json
import os
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from typing import Any, Dict

from uns_metadata_sync.db import Connection, connect

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

"""
Ingest a Sparkplug DBIRTH JSON fixture into a local PostgreSQL database.

Defaults pull connection details from PG* environment variables. Optionally
apply migrations before ingest. Timings for each phase are printed to help
identify performance bottlenecks.

Example:
  uv run python scripts/ingest_fixture.py \
    --apply-migrations \
    --fixture tests/fixtures/messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json
"""


def _scalar(row: Any) -> int:
    if row is None:
        return 0
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


@contextmanager
def _timed(label: str, sink: Dict[str, float]):
    start = perf_counter()
    try:
        yield
    finally:
        sink[label] = sink.get(label, 0.0) + (perf_counter() - start)


def _value_type_to_db_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int" if -2147483648 <= value <= 2147483647 else "long"
    if isinstance(value, float):
        return "double"
    return "string"


def _extract_metric_value(metric_entry: Dict[str, Any]) -> Any:
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


def _props_array_to_dict(props: Dict[str, Any] | None) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
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


def _connect(conninfo: str | None) -> Connection:
    if conninfo:
        return connect(conninfo)
    return connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "uns_metadata"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        options="-c search_path=uns_meta,public",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest DBIRTH fixture into Postgres")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(
            "tests/fixtures/messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json"
        ),
        help="Path to the JSON fixture",
    )
    parser.add_argument(
        "--group",
        default="Secil",
        help="UNS group identifier",
    )
    parser.add_argument(
        "--edge",
        default="Maceira-Ignition-Edge",
        help="Edge node name",
    )
    parser.add_argument(
        "--device",
        default="Kiln-K1",
        help="Device name",
    )
    parser.add_argument(
        "--conninfo",
        default=None,
        help="psycopg connection string (overrides PG* env vars)",
    )
    parser.add_argument(
        "--apply-migrations",
        action="store_true",
        help="Apply UNS migrations before ingest",
    )
    args = parser.parse_args()

    if not args.fixture.exists():
        raise SystemExit(f"Fixture not found: {args.fixture}")

    timings: Dict[str, float] = {}
    overall_start = perf_counter()

    with _timed("parse_fixture", timings):
        data = json.loads(args.fixture.read_text(encoding="utf-8"))

    with _timed("connect_db", timings):
        conn = _connect(args.conninfo)
        conn.autocommit = False

    with conn, conn.transaction():
        if args.apply_migrations:
            with _timed("apply_migrations", timings):
                apply_migrations(conn=conn)
                conn.execute("SET search_path TO uns_meta, public")

        with _timed("init_repository", timings):
            repo = MetadataRepository(conn)

        # Keep the ingest fast by avoiding per-commit fsyncs during bulk work.
        conn.execute("SET LOCAL synchronous_commit = off")

        device_payload = DevicePayload(
            group_id=args.group,
            country="PT",
            business_unit="Cement",
            plant="OUT",
            edge=args.edge,
            device=args.device,
            uns_path=normalize_device_path(
                group=args.group, edge_node=args.edge, device=args.device
            ),
        )

        with _timed("upsert_device", timings):
            dev_result = repo.upsert_device(device_payload)
        device_id = dev_result.record["device_id"]

        metrics = data.get("metrics", [])
        metric_payloads = []
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
            metric_payloads.append(
                MetricPayload(
                    device_id=device_id,
                    name=metric_name,
                    uns_path=normalize_metric_path(
                        group=args.group,
                        edge_node=args.edge,
                        device=args.device,
                        metric_name=metric_name,
                    ),
                    datatype=str(datatype_name),
                )
            )

        with _timed("upsert_metrics_bulk", timings):
            metric_id_map = repo.upsert_metrics_bulk(metric_payloads, batch_size=5000)

        property_payloads = []
        for metric_entry in metrics:
            metric_name = metric_entry.get("name")
            if not metric_name:
                continue
            metric_id = metric_id_map.get(metric_name)
            if not metric_id:
                continue

            props = _props_array_to_dict(metric_entry.get("properties"))
            if props:
                for key, prop_value in props.items():
                    property_payloads.append(
                        MetricPropertyPayload(
                            metric_id=metric_id,
                            key=key,
                            type=_value_type_to_db_type(prop_value),
                            value=prop_value,
                        )
                    )

        with _timed("upsert_metric_properties_bulk", timings):
            repo.upsert_metric_properties_bulk(
                property_payloads,
                batch_size=10000,
                manage_transaction=False,
            )

        with _timed("final_counts", timings):
            device_count = _scalar(
                conn.execute("SELECT COUNT(*) FROM uns_meta.devices").fetchone()
            )
            metric_count = _scalar(
                conn.execute("SELECT COUNT(*) FROM uns_meta.metrics").fetchone()
            )
            property_count = _scalar(
                conn.execute(
                    "SELECT COUNT(*) FROM uns_meta.metric_properties"
                ).fetchone()
            )

        with _timed("sample_query", timings):
            sample = conn.execute(
                """
                SELECT key, type, COALESCE(
                    value_string,
                    value_int::text,
                    value_long::text,
                    value_float::text,
                    value_double::text,
                    value_bool::text
                ) AS value
                  FROM uns_meta.metric_properties
                 WHERE key = 'DataPermission'
                 LIMIT 1
                """
            ).fetchone()

    total_time = perf_counter() - overall_start

    print(
        f"Ingest complete: devices={device_count}, metrics={metric_count}, properties={property_count}"
    )
    if sample:
        if isinstance(sample, dict):
            key = sample.get("key")
            value_type = sample.get("type")
            value = sample.get("value")
        else:
            key, value_type, value = sample
        print(f"Sample property: key={key} type={value_type} value={value}")

    print("Timings (seconds):")
    for label, duration in sorted(timings.items()):
        print(f"  {label}: {duration:.3f}")
    print(f"  total_elapsed: {total_time:.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
