from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from uns_metadata_sync.config import Settings
from uns_metadata_sync.db import connect_from_settings
from uns_metadata_sync.db.repository import (
    DevicePayload,
    MetadataRepository,
    MetricPayload,
    MetricPropertyPayload,
)
from uns_metadata_sync.path_normalizer import (
    normalize_device_path,
    normalize_metric_path,
)


FIXTURE = Path("tests/fixtures/messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json")


def _load_fixture() -> Dict[str, Any]:
    txt = FIXTURE.read_text(encoding="utf-8")
    return json.loads(txt)


def _parse_topic(topic: str) -> Optional[tuple[str, str, Optional[str]]]:
    """Parse a Sparkplug DBIRTH/NBIRTH topic.

    Returns a tuple (group, edge, device?) when topic matches:
      spBv1.0/<group>/<NBIRTH|DBIRTH>/<edge>[/<device>]
    """

    parts = topic.split("/")
    if len(parts) < 4 or parts[0].lower() != "spbv1.0":
        return None
    group = parts[1]
    msg_type = parts[2].upper()
    edge = parts[3]
    device = parts[4] if len(parts) > 4 else None
    if msg_type not in {"NBIRTH", "DBIRTH"}:
        return None
    return group, edge, device


def _value_type_to_db_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int" if -2147483648 <= value <= 2147483647 else "long"
    if isinstance(value, float):
        return "double"
    return "string"


def _metric_datatype_name(raw: Any) -> str:
    # If the fixture gives a string datatype, use it; otherwise infer from value
    if isinstance(raw, str) and raw:
        return raw
    if isinstance(raw, (int, float, bool)) or raw is None:
        return _value_type_to_db_type(raw)
    return "string"


def _extract_dimension(metrics: List[Dict[str, Any]], key: str, default: str) -> str:
    target = key.lower()
    for m in metrics:
        name = str(m.get("name", "")).lower()
        if name == target:
            val = m.get("value")
            if isinstance(val, str):
                val = val.strip()
                if val:
                    return val
            elif val is not None:
                return str(val)
    return default


def _read_fallback_context() -> Optional[tuple[str, str, str]]:
    """Read fallback device identity from env when fixture lacks topic/frame.

    Expected variables: FIXTURE_GROUP, FIXTURE_EDGE, FIXTURE_DEVICE
    """

    g = os.getenv("FIXTURE_GROUP")
    e = os.getenv("FIXTURE_EDGE")
    d = os.getenv("FIXTURE_DEVICE")
    if g and e and d:
        return g, e, d
    return None


def _props_array_to_dict(props: dict) -> dict[str, object]:
    """Convert Sparkplug-style properties {keys:[], values:[]} to a flat dict."""

    out: dict[str, object] = {}
    if not props or "keys" not in props or "values" not in props:
        return out
    keys = props.get("keys") or []
    values = props.get("values") or []
    for key, value_entry in zip(keys, values):
        # choose the first present typed value
        for field in (
            "stringValue",
            "booleanValue",
            "intValue",
            "longValue",
            "floatValue",
            "doubleValue",
        ):
            if field in value_entry:
                out[str(key)] = value_entry[field]
                break
    return out


def main() -> None:
    # Build Settings from env (no implicit dotenv here to keep it explicit)
    settings = Settings(
        broker="",
        port=1883,
        username="",
        password="",
        topic_all="spBv1.0/+/DBIRTH/#",
        topic_nbirth_all="spBv1.0/+/NBIRTH/#",
        topic_dbirth_all="spBv1.0/+/DBIRTH/#",
        alias_cache_path=Path("alias_cache.json"),
        write_jsonl=False,
        jsonl_pattern="messages_{topic}.jsonl",
        auto_request_rebirth=True,
        rebirth_throttle_seconds=60,
        client_id="fixture-ingest",
        tls_insecure=True,
        db_mode="local",
        db_host=os.environ.get("PGHOST", "localhost"),
        db_port=int(os.environ.get("PGPORT", "5432")),
        db_name=os.environ.get("PGDATABASE", "uns_metadata"),
        db_user=os.environ.get("PGUSER", "postgres"),
        db_password=os.environ.get("PGPASSWORD", ""),
        db_schema=os.environ.get("PGSCHEMA", "uns_meta"),
    )

    data = _load_fixture()

    # Accept several fixture shapes:
    # 1) {"topic": "...", "metrics": [ {name,value,datatype?,props?} ... ]}
    # 2) {"frame": {"device_uns_path":..., "metrics":[...]}}  (already normalized)
    topic: Optional[str] = data.get("topic")
    frame: Optional[Dict[str, Any]] = data.get("frame")
    metrics: List[Dict[str, Any]] = data.get("metrics") or []
    fallback = _read_fallback_context()

    if frame:
        device_uns_path = frame.get("device_uns_path")
        metrics = frame.get("metrics") or []
        if not device_uns_path:
            raise SystemExit("fixture.frame.device_uns_path missing")
        parts = device_uns_path.split("/")
        if len(parts) < 2:
            raise SystemExit(
                "cannot derive group/edge/device from frame.device_uns_path"
            )
        group = parts[0]
        edge = parts[1]
        device = parts[2] if len(parts) > 2 else None
    else:
        if not topic:
            # Accept plain metrics fixture if fallback identity is provided
            if not fallback:
                raise SystemExit(
                    "fixture must include 'topic' or 'frame' (or set FIXTURE_GROUP/FIXTURE_EDGE/FIXTURE_DEVICE)"
                )
            group, edge, device = fallback
            device_uns_path = normalize_device_path(
                group=group, edge_node=edge, device=device
            )
        else:
            parsed = _parse_topic(topic)
            if not parsed:
                raise SystemExit(f"topic not recognized as Sparkplug birth: {topic}")
            group, edge, device = parsed
            if not device:
                raise SystemExit("DBIRTH expected; topic must include a device segment")
            device_uns_path = normalize_device_path(
                group=group, edge_node=edge, device=device
            )

    # Connect & upsert
    conn = connect_from_settings(settings)
    try:
        repo = MetadataRepository(conn)

        # Normalize metric entries from fixture shape => repo-friendly shape
        normalized_metrics: List[Dict[str, Any]] = []
        for m in metrics:
            # pick the first present typed value
            value = None
            for field in (
                "booleanValue",
                "intValue",
                "longValue",
                "floatValue",
                "doubleValue",
                "stringValue",
            ):
                if field in m:
                    value = m[field]
                    break
            props = _props_array_to_dict(m.get("properties") or {})
            normalized_metrics.append(
                {
                    "name": m.get("name"),
                    "value": value,
                    "datatype": _metric_datatype_name(m.get("datatype", value)),
                    "props": props,
                }
            )
        metrics = normalized_metrics

        # Dimensions can come as dedicated metrics (country/business_unit/plant)
        country = _extract_dimension(metrics, "country", default="UNKNOWN")
        business_unit = _extract_dimension(metrics, "business_unit", default="UNKNOWN")
        plant = _extract_dimension(
            metrics, "plant", default=edge if topic else "UNKNOWN"
        )

        dev = repo.upsert_device(
            DevicePayload(
                group_id=group,  # type: ignore[arg-type]
                country=country,
                business_unit=business_unit,
                plant=plant,
                edge=edge,  # type: ignore[arg-type]
                device=device,  # type: ignore[arg-type]
                uns_path=device_uns_path,  # type: ignore[arg-type]
            )
        )
        print("device:", dev.status, dev.record.get("device_id"))
        device_id = dev.record.get("device_id")
        if not device_id:
            raise SystemExit("device_id missing after upsert; aborting")

        # Upsert metrics + scalar properties
        for m in metrics:
            mname = m.get("name")
            if not mname:
                continue
            m_uns_path = m.get("uns_path") or normalize_metric_path(
                group=group,  # type: ignore[arg-type]
                edge_node=edge,  # type: ignore[arg-type]
                device=device,  # type: ignore[arg-type]
                metric_name=str(mname),
            )
            datatype = _metric_datatype_name(m.get("datatype", m.get("value")))
            met = repo.upsert_metric(
                MetricPayload(
                    device_id=device_id,
                    name=str(mname),
                    uns_path=m_uns_path,
                    datatype=datatype,
                )
            )
            metric_id = met.record.get("metric_id")
            print("metric:", mname, met.status, metric_id)

            props: Dict[str, Any] = m.get("props") or {}
            for key, value in props.items():
                ptype = _value_type_to_db_type(value)
                prop = repo.upsert_metric_property(
                    MetricPropertyPayload(
                        metric_id=metric_id,
                        key=str(key),
                        type=ptype,
                        value=value,
                    )
                )
                print("  property:", key, prop.status)
    finally:
        conn.close()
    print("Done. Verify in SQL as needed.")


if __name__ == "__main__":
    main()
