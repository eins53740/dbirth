---
id: EP-06
title: Canary Write API Integration (Rate Limit, Retries)
status: planned
owner: Product Trio (PM, Design, Tech Lead)
version: 1.0
sources:
  - ../Metadata Sync Microservice Solution Design - Release 1.1.md
  - ../Testing Specification - Metadata Sync Microservice - Release 1.0.md
  - ../apis/canary_saf_index.html
  - ../apis/canary_views_index.html
---

## Overview
Transform diffs into Canary Store & Forward `POST /api/v1/storeData` payloads (properties-only) using session-based auth, resolve dataset/tag paths via Views `POST /api/v2/browseTags`, and deliver reliably under a 500 rps cap with retries and circuit breaker.

## Problem / Why
Provide dependable propagation of metadata changes to Canary under varying load and transient failures.

## Outcome
- Session token acquired via `/getSessionToken`, kept alive, refreshed on `BadSessionToken`, and revoked on shutdown.
- Dataset/path resolved via Views `/browseTags`, including pagination (`continuation`) and deep search.
- "Test dataset" mode forces writes to `Test` with `autoCreateDatasets=true` for validation; disabled by default in prod.
- Correct payload mapping; rate limiter enforcing 500 rps; exponential backoff with jitter; circuit breaker with recovery.

## Scope
Update (in addition to existing):
- In: HTTP client with timeouts; API-token auth; SAF session lifecycle (`/getSessionToken`, `/keepAlive`, `/revokeSessionToken`); SAF `/storeData`; Views `/browseTags` for dataset resolution; queue/rate limit; retry + circuit; de-duplication; Test dataset mode.
- Out: Dataset creation workflows in prod (except when explicitly enabled in Test mode); user-token auth flows; bulk sync beyond diffs.
- In: HTTP client with timeouts; token auth; queue/rate limit; retry + circuit; de‑duplication.
- Out: Canary read APIs and bulk sync beyond diffs.

## Dependencies
- Canary SAF v1 and Views v2 endpoints; shared API token.
- Canary endpoint, token; network egress.

## Acceptance Criteria (mapped tests)
- Session token acquired and cached; `BadSessionToken` triggers refresh; keepAlive sent after idle threshold.
- Views `/browseTags` resolves correct dataset/path (handles `deep`, `continuation`).
- Test dataset override enforces writes to `Test` only when enabled.
- TC‑20: Payload contract validated.
- TC‑21: Rate limit respected under sustained load.
- TC‑22: Retries and circuit breaker operate and recover.

## Stories
- Session token manager with keepAlive and refresh.
- Dataset/path resolver using Views browse APIs with pagination.
- Test dataset mode with guardrails.
- Mapper from internal model to Canary request.
- Token‑bucket limiter; bounded queue; backpressure behavior.
- Retry policy (6 attempts) with jitter; circuit breaker with half‑open.

## Risks / Mitigations
- Only production Canary available → Use `Test` dataset with hard override; DLQ for dataset-not-found in prod.
- Long Canary outages → Queue backpressure + circuit breaker; observability/alerts.

## Definition of Done
- Session reuse with timely keepAlive; clean revoke on shutdown; refresh on `BadSessionToken`.
- Views dataset resolution proven in tests; Test dataset override validated.
- Zero 429s under configured load; consistent delivery with de‑duplication; metrics/logs show states.
