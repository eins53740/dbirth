---
epic_id: EP-06
epic_title: Canary Write API Integration (Rate Limit, Retries)
status: draft
last_updated: 2025-09-23
sources:
  - docs/epics/EP-06 - Canary Write API Integration (Rate Limit, Retries).md
  - docs/Metadata Sync Microservice Solution Design - Release 1.1.md
  - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md
  - docs/apis/canary_saf_index.html
  - docs/apis/canary_views_index.html
jira_defaults:
  parent_id: EP-06
  issue_type: Task
  priority: High
  labels:
    - uns-meta
    - ep06
---

## Unit Tests

#### [TBD-EP-06-UT-01] Canary payload mapper unit tests
- **Summary**: Canary payload mapper unit tests
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep06, unit-test
- **Description**:
  - **Background**: Mapper converts internal diff model into Canary API payload; requires thorough coverage.
  - **In Scope**:
    - Validate mapping of device/metric fields, canary_id, and properties.
    - Ensure optional fields handled per API contract.
    - Confirm payload size limits enforced with meaningful errors.
  - **Out of Scope**:
    - HTTP transport concerns.
  - **References**:
    - docs/epics/EP-06 - Canary Write API Integration (Rate Limit, Retries).md
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-20)
- **Acceptance Criteria**:
  - [ ] Unit tests cover happy path and edge cases (missing optional fields, large property sets).
  - [ ] Payload output aligns with documented JSON examples.
  - [ ] Errors reference metric identity for debugging.

#### [TBD-EP-06-UT-02] Rate limiter and queue behavior tests
- **Summary**: Rate limiter and queue behavior tests
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep06, unit-test
- **Description**:
  - **Background**: Need deterministic tests verifying 500 rps token bucket and queue backpressure.
  - **In Scope**:
    - Simulate burst load and ensure limiter enforces ceiling.
    - Validate drop/timeout behavior when queue full.
    - Confirm metrics reflect queue depth and throttle events.
  - **Out of Scope**:
    - External monitoring configuration (EP-08).
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-21)
- **Acceptance Criteria**:
  - [ ] Tests assert no more than 500 requests dispatched per second.
  - [ ] Queue overflow triggers configured backpressure response.
  - [ ] Metrics counters increment for throttled events.

#### [TBD-EP-06-UT-03] Retry and circuit breaker logic tests
- **Summary**: Retry and circuit breaker logic tests
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep06, unit-test
- **Description**:
  - **Background**: Reliable delivery hinges on correct retry with jitter and circuit breaker transitions.
  - **In Scope**:
    - Unit tests simulating transient failures, respect for exponential backoff with jitter.
    - Verify circuit transitions closed -> open -> half-open -> closed.
    - Ensure dead-letter callback triggered after max retries.
  - **Out of Scope**:
    - Actual HTTP call integration.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-22)
- **Acceptance Criteria**:
  - [ ] Retry schedule matches documentation (6 attempts, capped delay).
  - [ ] Circuit breaker state and metrics update correctly.
  - [ ] Dead-letter handler invoked with detailed failure context.

## Integration Tests

#### [TBD-EP-06-IT-01] CDC consumer to Canary client integration
- **Summary**: CDC consumer to Canary client integration
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep06, integration-test
- **Description**:
  - **Background**: Need end-to-end validation from CDC diff queue to Canary API mock.
  - **In Scope**:
    - Feed debounced diffs from EP-05 harness into client.
    - Mock Canary API with controllable latency and failure modes.
    - Measure throughput, success rates, and retried deliveries.
  - **Out of Scope**:
    - Production Canary endpoint.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (DI-05)
- **Acceptance Criteria**:
  - [ ] Integration test demonstrates successful delivery under normal conditions.
  - [ ] Failure scenarios trigger retries and eventual success or DLQ per design.
  - [ ] Metrics/logs captured for rate limiting and circuit state.

#### [TBD-EP-06-IT-02] Rate limit soak test
- **Summary**: Rate limit soak test
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep06, integration-test
- **Description**:
  - **Background**: Validate sustained throughput at 450 rps without breaching Canary cap.
  - **In Scope**:
    - Drive workload for 15 minutes using synthetic diffs.
    - Monitor limiter metrics, queue depth, and CPU usage.
    - Produce report summarizing headroom and recommendations.
  - **Out of Scope**:
    - Production performance testing.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.1.md (Performance budgets)
- **Acceptance Criteria**:
  - [ ] Soak test shows zero 429 responses and stable queue depth.
  - [ ] Report stored under `docs/reports/canary-rate-limit.md`.
  - [ ] Recommendations included for scaling.

## Contract Tests

#### [TBD-EP-06-CT-01] Canary API contract verification
- **Summary**: Canary API contract verification
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep06, contract-test
- **Description**:
  - **Background**: Formalize contract with Canary `POST /api/v2/storeTagData` endpoint.
  - **In Scope**:
    - Generate OpenAPI snippet representing request/response.
    - Use Pact or similar framework to assert compatibility against mock server.
    - Document required headers, auth tokens, and error payloads.
  - **Out of Scope**:
    - Canary read APIs.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-20)
- **Acceptance Criteria**:
  - [ ] Contract tests fail on breaking change from Canary team.
  - [ ] OpenAPI fragment stored in `docs/contracts/canary_storeTagData.yaml`.
  - [ ] Change management process documented for contract updates.

## Implementation

#### [TBD-EP-06-IMP-01] Implement Canary client with rate limiter
- **Summary**: Implement Canary client with rate limiter
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep06, implementation
- **Description**:
  - **Background**: Need production client that respects rate limits and integrates retries.
  - **In Scope**:
    - Build HTTP client with timeout, auth token management, and structured logging.
    - Integrate token bucket limiter and bounded queue.
    - Emit metrics for requests, retries, failures, and circuit state.
  - **Out of Scope**:
    - Bulk sync workflows.
  - **References**:
    - docs/epics/EP-06 - Canary Write API Integration (Rate Limit, Retries).md
- **Acceptance Criteria**:
  - [ ] Client meets rate limit guarantees and passes integration tests.
  - [ ] Metrics integrated into observability stack.
  - [ ] Configuration via `.env` validated at startup.

#### [TBD-EP-06-IMP-02] Implement DLQ/backoff policy
- **Summary**: Implement DLQ/backoff policy
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep06, implementation
- **Description**:
  - **Background**: Ensure unresolvable failures captured without data loss.
  - **In Scope**:
    - Add dead-letter queue storage (Postgres table or object storage) with retention policy.
    - Provide admin tooling for replay.
    - Document escalation procedure when DLQ growth detected.
  - **Out of Scope**:
    - Automated replay scheduling.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.1.md (Error handling)
- **Acceptance Criteria**:
  - [ ] DLQ entries include payload, error metadata, and retry count.
  - [ ] Replay tooling validated via integration test.
  - [ ] Alerts configured for DLQ threshold (ties into EP-08).

#### [TBD-EP-06-IMP-03] Write Canary integration runbook
- **Summary**: Write Canary integration runbook
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep06, documentation
- **Description**:
  - **Background**: Ops needs documented steps for auth rotation, rate limit tuning, and incident response.
  - **In Scope**:
    - Document auth token management, rotation checklist, and fallback.
    - Capture common failure codes with remediation steps.
    - Link to contract tests and integration harness instructions.
  - **Out of Scope**:
    - Canary-side runbooks.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.1.md (Operations)
- **Acceptance Criteria**:
  - [ ] Runbook stored at `docs/runbooks/canary-integration.md`.
  - [ ] Includes table of failure codes vs actions.
  - [ ] Reviewed by Canary integration stakeholders.

## Additional Unit Tests (Auth, Views)

#### [TBD-EP-06-UT-04] SAF session token manager tests
- **Summary**: SAF session token acquisition, keepAlive, and refresh tests
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep06, unit-test
- **Description**:
  - **Background**: Session-based auth requires deterministic behavior around idle keepAlive and BadSessionToken refresh.
  - **In Scope**:
    - Acquire via `/getSessionToken` using API token; cache token.
    - Send `/keepAlive` when idle > `CANARY_KEEPALIVE_IDLE_SECONDS` (± jitter).
    - Refresh on `BadSessionToken`.
  - **Out of Scope**:
    - Real HTTP integration.
  - **References**:
    - docs/apis/canary_saf_index.html
- **Acceptance Criteria**:
  - [ ] KeepAlive cadence honored with jitter; suppressed when recent writes occur.
  - [ ] BadSessionToken triggers immediate refresh and retry.
  - [ ] Metrics counters updated (keepalive_sent, session_refresh_total).

#### [TBD-EP-06-UT-05] Dataset resolution via Views browseTags
- **Summary**: Views `browseTags` resolution tests (deep search + pagination)
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep06, unit-test
- **Description**:
  - **Background**: Canary rolls datasets (`Secil`, `Secil2`, ...). We must resolve the correct dataset/fullPath before write.
  - **In Scope**:
    - Deep search with `maxSize` + `continuation` handling.
    - Exact `fullPath` match selection; fallback behavior when not found.
    - Honors `CANARY_DATASET_OVERRIDE=Test` to bypass resolution.
  - **Out of Scope**:
    - Views user-token authentication.
  - **References**:
    - docs/apis/canary_views_index.html
- **Acceptance Criteria**:
  - [ ] Resolver returns the correct dataset/root for sample paths.
  - [ ] Pagination exercised with continuation tokens.
  - [ ] Test override forces `Test` dataset.

## Additional Integration Tests

#### [TBD-EP-06-IT-03] Session + Views + SAF end-to-end (with Test dataset)
- **Summary**: End-to-end flow including SAF session, Views browse, and property-only writes
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep06, integration-test
- **Description**:
  - **Background**: Validate full pipeline with both APIs and Test dataset override.
  - **In Scope**:
    - Mock SAF `/getSessionToken`, `/keepAlive`, `/storeData` and Views `/browseTags`.
    - Drive diffs through client; confirm browse-before-write; confirm writes target `Test` when override enabled.
  - **Out of Scope**:
    - Production Canary endpoints.
  - **References**:
    - docs/apis/canary_saf_index.html, docs/apis/canary_views_index.html
- **Acceptance Criteria**:
  - [ ] Flow succeeds under normal conditions with no 429s.
  - [ ] Session refresh occurs when forced `BadSessionToken` is injected.
  - [ ] Writes go to `Test` when override is enabled; prevented otherwise.

## Additional Contract Tests

#### [TBD-EP-06-CT-02] SAF session and Views browse contract
- **Summary**: Contract verification for `/getSessionToken`, `/keepAlive`, `/storeData`, and `/browseTags`
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep06, contract-test
- **Description**:
  - **Background**: Formalize request/response structures for SAF session and Views browse endpoints.
  - **In Scope**:
    - OpenAPI fragments for the above endpoints (auth headers/body, status codes, errors).
    - Pact (or similar) assertions against mocks.
  - **Out of Scope**:
    - User-token auth flows.
  - **References**:
    - docs/apis/canary_saf_index.html, docs/apis/canary_views_index.html
- **Acceptance Criteria**:
  - [ ] OpenAPI fragments stored in `docs/contracts/canary_saf_and_views.yaml`.
  - [ ] Contract tests fail on breaking changes.

## Additional Implementation

#### [TBD-EP-06-IMP-04] Implement SAF session token manager
- **Summary**: Session acquisition, keepAlive, refresh, and revoke
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep06, implementation
- **Description**:
  - **Background**: SAF requires session token lifecycle management.
  - **In Scope**:
    - Acquire `/getSessionToken` using `CANARY_API_TOKEN`, `CANARY_CLIENT_ID`, `CANARY_HISTORIANS`.
    - KeepAlive after idle threshold with jitter; refresh on `BadSessionToken`.
    - Revoke on shutdown; metrics for lifecycle events.
  - **Out of Scope**:
    - Multi-session sharding.
- **Acceptance Criteria**:
  - [ ] Configurable via `.env` vars (`*_KEEPALIVE_*`, `*_TIMEOUT_*`).
  - [ ] Metrics exported and covered by unit tests.

#### [TBD-EP-06-IMP-05] Implement Views dataset resolver
- **Summary**: Browse to resolve dataset/root for a canary path
- **Issue Type**: Task
- **Parent ID**: EP-06
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep06, implementation
- **Description**:
  - **Background**: Dataset capacity rollover requires resolving `Secil*` roots.
  - **In Scope**:
    - Use `/browseTags` with `deep=true` and pagination.
    - Prefer exact `fullPath` match; surface not-found with DLQ code (`DATASET_NOT_FOUND`) in prod.
    - Honor `CANARY_DATASET_OVERRIDE=Test` to force target dataset.
- **Acceptance Criteria**:
  - [ ] Resolver returns dataset/root and final tag path for a given UNS/canary path.
  - [ ] Pagination handled; errors surfaced with actionable codes.
