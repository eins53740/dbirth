#!/usr/bin/env python
"""Send controlled metadata updates to Canary Test dataset."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Dict, List, Optional

from uns_metadata_sync.canary import (
    CanaryClient,
    CanaryClientMetrics,
    CanaryClientSettings,
    CanaryDiff,
    CanaryPayloadMapper,
    SAFSessionManager,
)
from uns_metadata_sync.config import load_settings


def _parse_props(pairs: List[str]) -> Dict[str, str]:
    properties: Dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"Invalid property '{item}'. Expected format key=value")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Property key missing in '{item}'")
        properties[key] = value
    return properties


def _build_payload(diffs: List[CanaryDiff]) -> str:
    mapper = CanaryPayloadMapper()
    payload = mapper.build_payload(session_token="<redacted>", diffs=diffs)
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send a small batch of property updates to the Canary Test dataset",
    )
    parser.add_argument(
        "--path",
        dest="paths",
        action="append",
        required=True,
        help="Full UNS metric path (must start with Test/). Repeat for multiple tags.",
    )
    parser.add_argument(
        "--prop",
        dest="props",
        action="append",
        default=["description=Smoke test update"],
        help="Property to send in key=value form. Applies to every path. Repeat as needed.",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=5,
        help="Temporary request rate cap for the smoke run (default 5 rps)",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=1,
        help="Number of retry attempts after the initial send (default 1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload that would be sent and exit",
    )
    args = parser.parse_args()

    properties = _parse_props(args.props)
    settings = load_settings()

    if not settings.canary_api_token:
        print("Error: CANARY_API_TOKEN is not configured", file=sys.stderr)
        return 2
    if not settings.canary_base_url:
        print("Error: CANARY_SAF_BASE_URL is not configured", file=sys.stderr)
        return 2

    diffs: List[CanaryDiff] = []
    for path in args.paths:
        normalized = path.strip()
        if not normalized:
            continue
        if not normalized.startswith("Test/"):
            print(
                f"Refusing to send to non-Test dataset path: {normalized}",
                file=sys.stderr,
            )
            return 2
        diffs.append(
            CanaryDiff(
                uns_path=normalized,
                properties=dict(properties),
                metadata={
                    "source": "canary_write_smoke",
                    "request_id": str(uuid.uuid4()),
                },
            )
        )

    if not diffs:
        print("No valid paths supplied.", file=sys.stderr)
        return 2

    if args.dry_run:
        rendered = _build_payload(diffs)
        print("Dry run payload (session token redacted):")
        print(rendered)
        return 0

    client_settings = CanaryClientSettings(
        base_url=settings.canary_base_url,
        rate_limit_rps=max(1, args.rate_limit),
        burst_size=max(1, args.rate_limit),
        queue_capacity=settings.canary_queue_capacity,
        max_batch_tags=min(settings.canary_max_batch_tags, len(diffs)),
        max_payload_bytes=settings.canary_max_payload_bytes,
        request_timeout_seconds=settings.canary_request_timeout_seconds,
        retry_attempts=max(0, args.retry_attempts),
        retry_base_delay_seconds=settings.canary_retry_base_delay_seconds,
        retry_max_delay_seconds=settings.canary_retry_max_delay_seconds,
        circuit_consecutive_failures=settings.canary_circuit_consecutive_failures,
        circuit_reset_seconds=settings.canary_circuit_reset_seconds,
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

    metrics = CanaryClientMetrics()
    client: Optional[CanaryClient] = None
    try:
        client = CanaryClient(
            client_settings,
            session_manager=session_manager,
            metrics=metrics,
            auto_start=False,
        )
        for diff in diffs:
            client.enqueue(diff)
        while client.drain_once():
            continue
    finally:
        if client is not None:
            client.stop()
        session_manager.revoke()
        session_manager.close()

    snapshot = metrics.snapshot()
    print("Canary write smoke test completed.")
    print(
        f"Requests={snapshot['requests_total']} Success={snapshot['success_total']}"
        f" Retries={snapshot['retry_total']} Failures={snapshot['failure_total']}"
    )
    if snapshot.get("dead_letter_total"):
        print("Warning: dead-lettered entries detected!", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
