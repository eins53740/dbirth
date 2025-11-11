#!/usr/bin/env python
"""Generate CDC changes for Canary Test dataset by updating UNS metadata."""

from __future__ import annotations

import argparse
import contextlib
import threading
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from uns_metadata_sync.config import load_settings
from uns_metadata_sync.db import connect, connect_from_settings
from uns_metadata_sync.db.repository import (
    DevicePayload,
    MetadataRepository,
    MetricPayload,
    MetricPropertyPayload,
)
from uns_metadata_sync.db.lineage_writers import LineageVersionWriter
from uns_metadata_sync.cdc.checkpoint import InMemoryCheckpointStore
from uns_metadata_sync.cdc.service import (
    CDCListenerMetrics,
    CDCListenerService,
    build_cdc_listener,
)
from uns_metadata_sync.canary.client import (
    CanaryClient,
    CanaryClientMetrics,
    CanaryClientSettings,
    CanaryQueueFull,
)
from uns_metadata_sync.canary.session import SAFSessionManager


def _parse_props(pairs: Iterable[str], timestamp: str) -> Dict[str, str]:
    props: Dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"Invalid property '{item}'. Expected key=value")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Property key missing in '{item}'")
        props[key] = value.replace("{timestamp}", timestamp)
    return props


def _split_metric_path(metric_path: str) -> Tuple[str, str]:
    segments = [part for part in metric_path.split("/") if part]
    if len(segments) < 2:
        raise ValueError(
            f"Metric path '{metric_path}' must contain at least one device segment and metric name"
        )
    device_segments = segments[:-1]
    metric_name = segments[-1]
    return "/".join(device_segments), metric_name


def _device_payload_from_path(device_path: str) -> DevicePayload:
    segments = [part for part in device_path.split("/") if part]
    # Provide reasonable defaults for required fields
    group_id = segments[0] if segments else "Test"
    country = segments[1] if len(segments) > 1 else "TestCountry"
    business_unit = segments[2] if len(segments) > 2 else "TestBU"
    plant = segments[3] if len(segments) > 3 else "TestPlant"
    edge = segments[-2] if len(segments) > 1 else f"{group_id}-edge"
    device = segments[-1] if segments else "Device"
    return DevicePayload(
        group_id=group_id,
        country=country,
        business_unit=business_unit,
        plant=plant,
        edge=edge,
        device=device,
        uns_path=device_path,
    )


def _infer_type(value: str) -> str:
    try:
        int(value)
        return "int"
    except ValueError:
        try:
            float(value)
            return "double"
        except ValueError:
            pass
    if value.lower() in {"true", "false"}:
        return "boolean"
    return "string"


def _ensure_test_dataset(metric_paths: Iterable[str]) -> None:
    for path in metric_paths:
        if not path.startswith("Test/"):
            raise ValueError(f"Metric path '{path}' does not target the Test dataset")


@dataclass
class VerificationContext:
    canary_client: CanaryClient
    canary_metrics: CanaryClientMetrics
    session_manager: Optional[SAFSessionManager]
    cdc_service: CDCListenerService
    cdc_metrics: CDCListenerMetrics
    cdc_thread: threading.Thread


def _build_canary_components(
    settings,
) -> Tuple[CanaryClient, CanaryClientMetrics, Optional[SAFSessionManager]]:
    if not settings.canary_base_url or not settings.canary_api_token:
        raise RuntimeError(
            "Canary SAF settings missing. Set CANARY_SAF_BASE_URL and CANARY_API_TOKEN."
        )

    session_manager = SAFSessionManager(
        base_url=settings.canary_base_url,
        api_token=settings.canary_api_token,
        client_id=settings.canary_client_id or settings.client_id,
        historians=settings.canary_historians,
        session_timeout_ms=settings.canary_session_timeout_ms,
        keepalive_idle_seconds=settings.canary_keepalive_idle_seconds,
        keepalive_jitter_seconds=settings.canary_keepalive_jitter_seconds,
    )

    canary_settings = CanaryClientSettings(
        base_url=settings.canary_base_url,
        request_timeout_seconds=settings.canary_request_timeout_seconds,
        rate_limit_rps=settings.canary_rate_limit_rps,
        burst_size=settings.canary_rate_limit_rps,
        queue_capacity=settings.canary_queue_capacity,
        max_batch_tags=settings.canary_max_batch_tags,
        max_payload_bytes=settings.canary_max_payload_bytes,
        retry_attempts=settings.canary_retry_attempts,
        retry_base_delay_seconds=settings.canary_retry_base_delay_seconds,
        retry_max_delay_seconds=settings.canary_retry_max_delay_seconds,
        circuit_consecutive_failures=settings.canary_circuit_consecutive_failures,
        circuit_reset_seconds=settings.canary_circuit_reset_seconds,
    )

    metrics = CanaryClientMetrics()
    client = CanaryClient(
        canary_settings,
        session_manager=session_manager,
        metrics=metrics,
        auto_start=False,
        dead_letter_handler=lambda diff, error: print(
            f"[canary] dead-lettered {getattr(diff, 'uns_path', '<unknown>')}: {error}"
        ),
    )
    return client, metrics, session_manager


def _build_cdc_listener_with_sink(
    settings, diff_sink
) -> Tuple[CDCListenerService, CDCListenerMetrics]:
    metrics = CDCListenerMetrics(namespace="canary_cdc_smoke")
    service = build_cdc_listener(
        settings,
        diff_sink=diff_sink,
        checkpoint_store=InMemoryCheckpointStore(),
        metrics=metrics,
    )
    return service, metrics


def _ensure_replication_slot(settings) -> None:
    """Create the logical replication slot if it does not exist."""
    conn = None
    try:
        conn = connect(
            host=settings.pg_replication_host,
            port=settings.pg_replication_port,
            dbname=settings.pg_replication_database,
            user=settings.pg_replication_user,
            password=settings.pg_replication_password,
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT plugin FROM pg_replication_slots WHERE slot_name = %s",
                (settings.cdc_slot,),
            )
            row = cur.fetchone()
            if row:
                existing_plugin = row[0]
                if existing_plugin != settings.cdc_replication_plugin:
                    raise RuntimeError(
                        f"Replication slot '{settings.cdc_slot}' exists with plugin "
                        f"{existing_plugin!r}, expected {settings.cdc_replication_plugin!r}."
                    )
                return
            cur.execute(
                "SELECT slot_name, lsn "
                "FROM pg_create_logical_replication_slot(%s, %s)",
                (settings.cdc_slot, settings.cdc_replication_plugin),
            )
            slot_name, restart_lsn = cur.fetchone()
            print(
                f"[verify] Created replication slot {slot_name} "
                f"using plugin {settings.cdc_replication_plugin} (restart LSN {restart_lsn})."
            )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to ensure replication slot '{settings.cdc_slot}': {exc}"
        ) from exc
    finally:
        if conn is not None:
            conn.close()


def _start_verification(settings, *, expected: int) -> VerificationContext:
    if not settings.cdc_enabled:
        raise RuntimeError("CDC is disabled via configuration; set CDC_ENABLED=true.")
    if not settings.canary_enabled:
        raise RuntimeError(
            "Canary writer disabled via configuration; set CANARY_WRITER_ENABLED=true."
        )
    if settings.db_mode != "local":
        raise RuntimeError(
            f"CDC verification requires DB_MODE=local (current: {settings.db_mode})"
        )

    _ensure_replication_slot(settings)

    canary_client: Optional[CanaryClient] = None
    canary_metrics: Optional[CanaryClientMetrics] = None
    session_manager: Optional[SAFSessionManager] = None
    cdc_service: Optional[CDCListenerService] = None
    cdc_metrics: Optional[CDCListenerMetrics] = None
    cdc_thread: Optional[threading.Thread] = None

    try:
        client, metrics, sess = _build_canary_components(settings)
        canary_client = client
        canary_metrics = metrics
        session_manager = sess

        def _diff_sink(payload: Dict[str, object]) -> None:
            try:
                canary_client.enqueue(payload)
            except CanaryQueueFull:
                metric_path = payload.get("uns_path") or payload.get("metric")
                print(f"[cdc] Canary queue full - dropped diff for {metric_path}")

        cdc_service, cdc_metrics = _build_cdc_listener_with_sink(settings, _diff_sink)

        cdc_thread = threading.Thread(
            target=cdc_service.run_forever,
            name="canary-cdc-smoke",
            daemon=True,
        )
        canary_client.start()
        cdc_thread.start()
        return VerificationContext(
            canary_client=canary_client,
            canary_metrics=canary_metrics,
            session_manager=session_manager,
            cdc_service=cdc_service,
            cdc_metrics=cdc_metrics,
            cdc_thread=cdc_thread,
        )
    except Exception:
        if cdc_service is not None:
            with contextlib.suppress(Exception):
                cdc_service.stop()
        if cdc_thread is not None and cdc_thread.is_alive():
            with contextlib.suppress(Exception):
                cdc_thread.join(timeout=5)
        if canary_client is not None:
            with contextlib.suppress(Exception):
                canary_client.stop()
        if session_manager is not None:
            with contextlib.suppress(Exception):
                session_manager.revoke()
            with contextlib.suppress(Exception):
                session_manager.close()
        raise


def _await_verification(
    context: VerificationContext, *, expected: int, timeout: float
) -> bool:
    deadline = time.time() + timeout
    last_drain = 0.0
    while time.time() < deadline:
        success = context.canary_metrics.success_total
        dead_letters = context.canary_metrics.dead_letter_total
        failures = context.canary_metrics.failure_total
        if success >= expected:
            return True
        if dead_letters > 0:
            print("[verify] Canary dead-letter count > 0; failing early.")
            return False
        if failures > 0 and context.canary_metrics.circuit_state == "open":
            print("[verify] Canary circuit breaker open; aborting wait.")
            return False
        now = time.time()
        if now - last_drain >= 1.0:
            context.cdc_service.force_flush()
            context.canary_client.drain_once()
            last_drain = now
        time.sleep(1.0)
    return False


def _snapshot_metrics(
    context: VerificationContext,
) -> Tuple[Dict[str, float], Dict[str, int | str]]:
    cdc_snapshot = context.cdc_metrics.snapshot()
    canary_snapshot = context.canary_metrics.snapshot()
    return cdc_snapshot, canary_snapshot


def _shutdown_verification(context: VerificationContext) -> None:
    with contextlib.suppress(Exception):
        context.cdc_service.stop()
    if context.cdc_thread.is_alive():
        with contextlib.suppress(Exception):
            context.cdc_thread.join(timeout=5)
    with contextlib.suppress(Exception):
        context.canary_client.stop()
    if context.session_manager is not None:
        with contextlib.suppress(Exception):
            context.session_manager.revoke()
        with contextlib.suppress(Exception):
            context.session_manager.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upsert UNS metadata rows to trigger CDC and Canary writes for the Test dataset",
    )
    parser.add_argument(
        "--metric-path",
        dest="metric_paths",
        action="append",
        required=True,
        help="Full UNS metric path (e.g. Test/Smoke/Device/Temperature). Repeat for multiple tags.",
    )
    parser.add_argument(
        "--prop",
        dest="props",
        action="append",
        default=["description=Smoke test {timestamp}"],
        help="Property to write in key=value form. Use {timestamp} placeholder for uniqueness.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the operations without modifying the database",
    )
    parser.add_argument(
        "--verify-cdc",
        action="store_true",
        help="Run the CDC listener and assert that diffs are delivered to Canary",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Seconds to wait for CDC + Canary success when verifying (default: 45)",
    )
    parser.add_argument(
        "--expected",
        type=int,
        default=None,
        help="Expected number of Canary successes when verifying (default: metric count)",
    )
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).isoformat()
    _ensure_test_dataset(args.metric_paths)
    props = _parse_props(args.props, timestamp)

    if args.verify_cdc and args.dry_run:
        parser.error("--verify-cdc cannot be combined with --dry-run")

    if args.dry_run:
        print("Dry run - planned operations:")
        for metric_path in args.metric_paths:
            print(f"  {metric_path} -> {props}")
        return 0

    settings = load_settings()
    conn = connect_from_settings(settings)

    verification_context: Optional[VerificationContext] = None
    expected_payloads = (
        args.expected if args.expected is not None else max(len(args.metric_paths), 1)
    )

    if args.verify_cdc:
        print(
            f"[verify] Starting CDC listener and Canary client "
            f"(expected payloads: {expected_payloads}, timeout: {args.timeout:.0f}s)"
        )
        verification_context = _start_verification(
            settings,
            expected=expected_payloads,
        )

    try:
        repo = MetadataRepository(conn)
        version_writer = LineageVersionWriter(conn)
        for metric_path in args.metric_paths:
            device_path, metric_name = _split_metric_path(metric_path)
            device_payload = _device_payload_from_path(device_path)
            device_result = repo.upsert_device(device_payload)
            device_id = device_result.record["device_id"]

            metric_payload = MetricPayload(
                device_id=device_id,
                name=metric_name,
                uns_path=metric_path,
                datatype="string",
            )
            metric_result = repo.upsert_metric(metric_payload)
            metric_id = metric_result.record["metric_id"]

            property_payloads = [
                MetricPropertyPayload(
                    metric_id=metric_id,
                    key=key,
                    type=_infer_type(value),
                    value=value,
                )
                for key, value in props.items()
            ]
            repo.upsert_metric_properties_bulk(property_payloads)

            diff_payload = {key: value for key, value in props.items()}
            version_writer.apply(
                metric_id=metric_id,
                new_uns_path=metric_path,
                diff=diff_payload,
                previous_uns_path=metric_path,
                changed_by="canary_cdc_smoke",
            )

            print(
                f"Updated {metric_path} with properties: "
                + ", ".join(f"{k}={v}" for k, v in props.items())
            )

        if verification_context is not None:
            success = _await_verification(
                verification_context,
                expected=expected_payloads,
                timeout=max(args.timeout, 1.0),
            )
            cdc_metrics, canary_metrics = _snapshot_metrics(verification_context)
            print("[verify] CDC metrics snapshot:")
            for key in sorted(cdc_metrics):
                print(f"  {key}: {cdc_metrics[key]}")
            print("[verify] Canary metrics snapshot:")
            for key in sorted(canary_metrics):
                print(f"  {key}: {canary_metrics[key]}")
            if success:
                print("[verify] CDC + Canary verification succeeded.")
            else:
                print("[verify] CDC + Canary verification FAILED.")
                return 1

        print(
            "Done. CDC should emit the diffs; monitor the service logs and DLQ backlog."
        )
    finally:
        if verification_context is not None:
            _shutdown_verification(verification_context)
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
