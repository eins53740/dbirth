---
title: Canary Integration Runbook
status: draft
owner: UNS Metadata Team
last_updated: 2025-10-21
sources:
  - ../Metadata Sync Microservice Solution Design - Release 1.1.md
  - ../apis/canary_saf_index.html
  - ../apis/canary_views_index.html
---

## Overview
- Purpose: end‑to‑end operational guidance for the Canary Write API integration used to propagate UNS metadata changes.
- Scope: configuration, deployment, validation, rate limiting, retries/circuit breaker, DLQ handling and replay, monitoring/alerting, incident response, and token/dataset management.

## Before You Begin
- You have applied the latest migrations (includes `uns_meta.canary_dlq`). See `docs/playbooks/postgresql-local-setup.md:5` for commands.
- Environment contains Canary endpoints and token in `.env`.
- Outbound HTTPS allowed from the service host to Canary SAF/Views endpoints.

## Architecture (runtime path)
- CDC diffs → Canary Client → token‑bucket limiter → HTTP `POST /api/v1/storeData` (properties‑only)
- On unresolvable failure after retries → persist to `uns_meta.canary_dlq` → operator replays later via `scripts/replay_dlq.py`.
- Optional: session lifecycle against SAF (`/api/v1/getSessionToken`, `/keepAlive`, `/revokeSessionToken`) when enabled.

## Configuration (.env)
- Writer toggles and endpoints
  - `CANARY_WRITER_ENABLED` (default auto‑enabled if URL+token present): set `false` to temporarily pause writes.
  - `CANARY_SAF_BASE_URL`, `CANARY_VIEWS_BASE_URL`: base URLs (no trailing slash required).
  - `CANARY_API_TOKEN`: Canary API token.
  - `CANARY_CLIENT_ID`: client identity used by SAF.
  - `CANARY_HISTORIANS`: comma‑separated historian targets.
- Rate limiting & retries
  - `CANARY_RATE_LIMIT_RPS`: max requests per second (default 500).
  - `CANARY_QUEUE_CAPACITY`: in‑memory queue to absorb bursts.
  - `CANARY_MAX_BATCH_TAGS`: number of tags per request batch (default 100).
  - `CANARY_MAX_PAYLOAD_BYTES`: guardrail for payload size (default 1 MB).
  - `CANARY_REQUEST_TIMEOUT_SECONDS`: per‑request timeout (default 10s).
  - `CANARY_RETRY_ATTEMPTS`: number of retry attempts after the initial send (default 6).
  - `CANARY_RETRY_BASE_DELAY_SECONDS`, `CANARY_RETRY_MAX_DELAY_SECONDS`: exponential backoff with jitter.
  - `CANARY_CIRCUIT_CONSECUTIVE_FAILURES`, `CANARY_CIRCUIT_RESET_SECONDS`: circuit breaker thresholds.
- Session lifecycle
  - `CANARY_SESSION_TIMEOUT_MS`: SAF session timeout hint in milliseconds (default 120000).
  - `CANARY_KEEPALIVE_IDLE_SECONDS`: idle seconds before sending keepAlive (default 30).
  - `CANARY_KEEPALIVE_JITTER_SECONDS`: random jitter added to keepAlive timing (default 10).

- DLQ retention and operations
  - `CANARY_DLQ_TTL_SECONDS`: seconds to retain failed entries (default 604800 / 7 days).
  - `CANARY_DLQ_ALERT_THRESHOLD`: backlog depth to alert on (default 500).
  - `CANARY_DLQ_REPLAY_BATCH_SIZE`: default replay batch size (default 50).
- Dataset behavior
  - `CANARY_DATASET_PREFIX`: base dataset name (e.g., `Secil`).
  - `CANARY_DATASET_OVERRIDE`: set to `Test` to force writes into a test dataset.

## Deployment
1. Set/verify `.env` variables. Secrets like `CANARY_API_TOKEN` should come from your secrets store and not be committed.
2. Restart the service so new configuration loads.
3. Confirm startup logs show the Canary client initialised and CDC enabled if desired.

## Validation (smoke)
- Unit quick check: `uv run pytest -m unit -q`
- Canary client integration harness (no external Canary required): `uv run pytest tests/integration/test_cdc_to_canary_client.py -q`
- Confirm `uns_meta.canary_dlq` exists: `SELECT to_regclass('uns_meta.canary_dlq');` returns non‑NULL.

### Write smoke tests
1. Direct write (Path A) using the Canary client:
   ```bash
   uv run python scripts/canary_write_smoke.py \
     --path Test/Smoke/DeviceA/Temperature \
     --prop description="Smoke test {timestamp}" \
     --dry-run
   ```
   Remove `--dry-run` to send the request. Metrics summary prints on completion; expect `Failures=0` and `dead_letter_total=0`.

2. CDC-driven (Path B) to exercise the pipeline end-to-end (service + CDC listener must be running):
   ```bash
   uv run python scripts/canary_cdc_smoke.py \
     --metric-path Test/Smoke/DeviceA/Temperature \
     --prop description="Smoke test {timestamp}"
   ```
   This upserts metadata into Postgres, generating CDC diffs that the running service will send to Canary. Monitor service logs and the DLQ backlog.

## Canary Request Basics
- Endpoint: `POST /api/v1/storeData`
- Base URL: `CANARY_SAF_BASE_URL` (e.g., https://host:port/api/v1)
- Authentication: obtain `sessionToken` via `POST /api/v1/getSessionToken` using `CANARY_API_TOKEN` and include it in requests. The service manages this automatically via the SAF session manager.
- Body (properties‑only diffs):
  - `sessionToken` (if SAF session used)
  - `properties`: `{ <canary_tag_id>: [[timestamp, "key=value", 192], ...], ... }`
- Example payload snippet:
```
{
  "sessionToken": "<token>",
  "properties": {
    "Secil.Portugal.Cement.Kiln.Temperature": [
      ["2025-01-01T12:00:00.000000Z", "engUnit=°C", 192],
      ["2025-01-01T12:00:00.000000Z", "displayHigh=1800", 192]
    ]
  }
}
```

## Rate Limiting & Retries (operator view)
- Enforced client‑side via token‑bucket: requests are spread to not exceed `CANARY_RATE_LIMIT_RPS`.
- Failures get exponential backoff with jitter across `CANARY_RETRY_ATTEMPTS` total tries.
- Circuit breaker opens after consecutive failures (default 20) to protect downstream; half‑opens after the reset window to probe.

## DLQ (Dead‑Letter Queue)
- Table: `uns_meta.canary_dlq` stores failed diffs (`payload` jsonb) with error metadata and retry count.
- Inspect backlog:
```
SELECT COUNT(*) AS pending
FROM uns_meta.canary_dlq
WHERE status = 'pending' AND (expires_at IS NULL OR expires_at > NOW());
```
- Purge expired:
```
DELETE FROM uns_meta.canary_dlq
WHERE expires_at IS NOT NULL AND expires_at <= NOW();
```
- Replay entries:
  - Dry run: `uv run python scripts/replay_dlq.py --limit 100`
  - Execute: `uv run python scripts/replay_dlq.py --execute --limit 100`
  - Notes: replay uses the same Canary client (respects rate limit/retries). Increase `--limit` gradually for large backlogs.

## Monitoring & Alerting
- Backlog alert (recommended): use the backlog query above; alert when `pending >= CANARY_DLQ_ALERT_THRESHOLD` for 5 minutes; critical at `>= 2×`.
- Useful health signals to track in dashboards/logs:
  - Request throughput & latency, retry count, throttled count, circuit state, queue depth.
  - DLQ backlog trend, replay counts, purge counts.
- Logs: on each DLQ insertion, service logs a warning when backlog exceeds threshold; wire this to your log‑alerting too.

## Common Issues & Actions
- 401/403 Authentication
  - Rotate `CANARY_API_TOKEN`, restart service, validate writes, replay DLQ.
- 429 Too Many Requests
  - Lower `CANARY_RATE_LIMIT_RPS`, watch throttled count and Canary feedback; queue may grow briefly and then drain.
- 5xx Server Errors / Canary outage
  - Expect retries and circuit open; monitor backlog; once Canary recovers, client resumes; replay residual DLQ if any.
- 400 Validation / schema mismatch
  - Compare diffs with contract and examples; fix mapper; replay DLQ.
- Dataset not found
  - Check dataset resolution or set `CANARY_DATASET_OVERRIDE=Test` for controlled testing; plan dataset rollover (e.g., `Secil2`).

## Operating Procedures
- Temporarily pause writes
  - Set `CANARY_WRITER_ENABLED=false` in `.env` and restart; resume by re‑enabling.
- Token rotation
  - Generate new token in Canary, update `.env`, restart service, validate and then revoke old token; replay any DLQ formed during rotation.
- Rate cap tuning
  - Start at 500 rps; reduce if Canary signals saturation (429), or increase only with vendor approval.
- Dataset override (Test)
  - Set `CANARY_DATASET_OVERRIDE=Test` to force a test dataset during validation; reset to empty once complete.

## Troubleshooting Cheatsheet
- Verify connectivity
  - `Test-NetConnection <host> -Port <port>` (Windows) or `curl -v <url>`
- Inspect recent errors
  - Grep logs for `dead-lettered` or `Canary request failed permanently`.
- Check DLQ TTL and purges
  - Ensure `CANARY_DLQ_TTL_SECONDS` is non‑zero; run purge SQL if needed.

## References
- Design: `docs/Metadata Sync Microservice Solution Design - Release 1.1.md`
- APIs: `docs/apis/canary_saf_index.html`, `docs/apis/canary_views_index.html`
- Replay helper: `scripts/replay_dlq.py`

## Auth & Session Lifecycle (SAF)
- Acquire: `POST /api/v1/getSessionToken` with `apiToken`, `historians`, `clientId`, `settings.clientTimeout`.
- KeepAlive: send `POST /api/v1/keepAlive` if idle > `CANARY_KEEPALIVE_IDLE_SECONDS` (± `CANARY_KEEPALIVE_JITTER_SECONDS`).
- Refresh: on `BadSessionToken`, reacquire token and retry.
- Revoke: `POST /api/v1/revokeSessionToken` on shutdown.

## Dataset Resolution (Views)
- Resolve using `POST /api/v2/browseTags` with `deep=true`; page using `maxSize` + `continuation`.
- Candidate roots: `CANARY_DATASET_PREFIX*` (e.g., `Secil`, `Secil2`, `Secil3`).
- Choose dataset where `fullPath` equals expected tag path; DLQ with `DATASET_NOT_FOUND` if not found (prod).

## Test Dataset Mode
- When `CANARY_DATASET_OVERRIDE=Test`, force writes to `Test`; enable `autoCreateDatasets=true` for that session only.
- Guardrail: prevent writes to other datasets while override is set.

## Rate Limits & Retries
- Global cap: 500 req/s; client enforces token-bucket limiter.
- Retries: 6 attempts, 10s timeout per attempt, exponential backoff with jitter.

## Monitoring & Metrics
- Session lifecycle: `saf_session_refresh_total`, `saf_keepalive_sent_total`, `saf_keepalive_errors_total`, `saf_session_uptime_seconds`.
- Client: requests_total, retries_total, failures_total, circuit_state, queue_depth.

## Common Failures & Actions
- 429 Too Many Requests: verify limiter config; reduce throughput; inspect circuit breaker.
- BadSessionToken: reacquire session; check token TTL and keepAlive cadence.
- Dataset not found: verify path; consider creating next `SecilN` dataset; reprocess DLQ.
- Network errors/timeouts: validate base URLs, TLS, firewall egress; consult Canary status.

## Secrets & Rotation
- `CANARY_API_TOKEN` managed in secrets store; rotate quarterly or on incident.
- Restart services post-rotation; verify session reacquisition.

## Change Management
- Contract changes tracked in `docs/contracts/canary_saf_and_views.yaml` and validated by contract tests.
