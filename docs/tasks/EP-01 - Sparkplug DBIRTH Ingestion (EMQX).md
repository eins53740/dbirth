---
epic_id: EP-01
epic_title: Sparkplug DBIRTH Ingestion (EMQX)
status: draft
last_updated: 2025-09-23
sources:
  - docs/epics/EP-01 - Sparkplug DBIRTH Ingestion (EMQX).md
  - docs/Metadata Sync Microservice Solution Design - Release 1.0.md
  - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md
jira_defaults:
  parent_id: EP-01
  issue_type: Task
  priority: High
  labels:
    - uns-meta
    - ep01
---

## Unit Tests

#### [TBD-EP-01-UT-01] Build MQTT DBIRTH subscription regression harness
- **Summary**: Build MQTT DBIRTH subscription regression harness
- **Issue Type**: Task
- **Parent ID**: EP-01
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep01, unit-test
- **Description**:
  - **Background**: Current MQTT client lacks automated regression coverage for clean session reconnects and QoS 0 duplicate delivery guarantees described in the design doc.
  - **In Scope**:
    - Create unit-level tests that simulate EMQX session drops, clean session reconnects, and topic re-subscription to spBv1.0/Secil/DBIRTH/#.
    - Assert watchdog callbacks fire within configured timeout when the subscription lags.
    - Cover duplicate DBIRTH delivery handling at the client layer before handing off to downstream processing.
  - **Out of Scope**:
    - Network integration with live EMQX brokers.
    - REBIRTH publish workflows (handled in EP-02).
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (MQTT ingest section)
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-10, TC-11)
- **Acceptance Criteria**:
  - [ ] Tests reproduce session drop and verify reconnect logic resubscribes before timeout.
  - [ ] Duplicate message fixtures do not increment downstream handoff counter.
  - [ ] Watchdog metric assertions cover success and failure paths.

#### [TBD-EP-01-UT-02] Validate TLS bootstrap and credential rotation helpers
- **Summary**: Validate TLS bootstrap and credential rotation helpers
- **Issue Type**: Task
- **Parent ID**: EP-01
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep01, unit-test
- **Description**:
  - **Background**: TLS configuration code must enforce TLS 1.3 ciphers and allow credential hot reload without restarts.
  - **In Scope**:
    - Add tests covering .env credential reload events and certificate parsing failures.
    - Confirm TLS context builder rejects protocols weaker than TLS 1.3 and logs actionable errors.
    - Verify secrets remain redacted in error messages per security guidelines.
  - **Out of Scope**:
    - mTLS handshake logic (future roadmap).
  - **References**:
    - docs/epics/EP-07 - Security & Configuration (TLS, Secrets).md
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (SEC-01)
- **Acceptance Criteria**:
  - [ ] Tests fail if TLS context allows TLS 1.2 or weaker.
  - [ ] Reloaded credentials take effect without process restart in unit harness.
  - [ ] Secret strings never appear in test log captures.

#### [TBD-EP-01-UT-03] Exercise MQTT retry and backoff utilities
- **Summary**: Exercise MQTT retry and backoff utilities
- **Issue Type**: Task
- **Parent ID**: EP-01
- **Priority**: Medium
- **Story Points**: 2
- **Labels**: uns-meta, ep01, unit-test
- **Description**:
  - **Background**: Retry helpers wrap MQTT connect attempts but lack assertions for jitter and cap logic.
  - **In Scope**:
    - Unit tests covering exponential backoff with jitter (0.5s seed, max 30s) and ensuring cap after configured attempts.
    - Validate retry hooks emit Prometheus metrics for successes and failures (per EP-08 observability expectations).
    - Simulate permanent failure to confirm helper surfaces terminal error.
  - **Out of Scope**:
    - Integration with global circuit breaker (EP-06).
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Resiliency patterns)
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-11)
- **Acceptance Criteria**:
  - [ ] Retry delay sequence matches design tolerances including jitter distribution bounds.
  - [ ] Metrics counters increment per attempt and final outcome.
  - [ ] Terminal failures bubble explicit error for caller handling.

## Integration Tests

#### [TBD-EP-01-IT-01] Prove MQTT ingest to Postgres write path
- **Summary**: Prove MQTT ingest to Postgres write path
- **Issue Type**: Task
- **Parent ID**: EP-01
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep01, integration-test
- **Description**:
  - **Background**: Need an automated integration suite that drives DBIRTH fixtures through the message handler into the staging Postgres instance.
  - **In Scope**:
    - Spin up EMQX test container with TLS enabled and load DBIRTH fixtures from ixtures/mqtt/dbirth.
    - Assert device and metric rows persist with normalized keys stubbed by EP-03 tasks.
    - Validate duplicate DBIRTH frames do not create extra rows by re-running ingest scenario.
  - **Out of Scope**:
    - Canary API calls or CDC emissions.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-10, DI-01)
    - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.0).md (devices, metrics tables)
- **Acceptance Criteria**:
  - [ ] Integration harness provisions EMQX and Postgres containers with seeded certs.
  - [ ] After ingest, tables contain expected rows matching fixture assertions.
  - [ ] Re-ingest of same payload results in zero additional inserts per audit query.

#### [TBD-EP-01-IT-02] Validate DB write error handling path
- **Summary**: Validate DB write error handling path
- **Issue Type**: Task
- **Parent ID**: EP-01
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep01, integration-test
- **Description**:
  - **Background**: Integration coverage required for error fan-out when Postgres rejects writes (e.g., TLS drop, constraint violation).
  - **In Scope**:
    - Inject transient TLS failure to ensure retry/backoff handles reconnect without data loss.
    - Force constraint violation using malformed payload and confirm message gets routed to DLQ or error metric.
    - Capture structured logs that include correlation id and failure reason.
  - **Out of Scope**:
    - Canary retry pipeline interactions.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Error handling)
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (DI-01, OBS-02)
- **Acceptance Criteria**:
  - [ ] Test harness exposes toggle for TLS interruption and verifies automatic recovery.
  - [ ] Constraint violation scenario triggers documented DLQ/error metric behavior.
  - [ ] Logs contain correlation ids and redacted secrets per security guidelines.

## Contract Tests

#### [TBD-EP-01-CT-01] Document EMQX broker contract baseline
- **Summary**: Document EMQX broker contract baseline
- **Issue Type**: Task
- **Parent ID**: EP-01
- **Priority**: Medium
- **Story Points**: 2
- **Labels**: uns-meta, ep01, contract-test
- **Description**:
  - **Background**: Need explicit contract tests around EMQX connection parameters, TLS negotiation, and topic filters to freeze expectations.
  - **In Scope**:
    - Capture broker capabilities (protocol, session flags, QoS support) using mocked handshake.
    - Produce failing test when server advertises unsupported cipher suite or mismatched topic regex.
    - Generate Markdown report consumed by ops runbook.
  - **Out of Scope**:
    - Payload decode (owned by EP-02).
  - **References**:
    - docs/epics/EP-07 - Security & Configuration (TLS, Secrets).md
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (SEC-01)
- **Acceptance Criteria**:
  - [ ] Contract test fixture asserts TLS negotiation uses documented cipher suites.
  - [ ] Topic filters verified against spBv1.0/Secil/DBIRTH/# pattern with regression coverage.
  - [ ] Generated report stored under docs/contracts/emqx.md and referenced in runbooks.

## Implementation

#### [TBD-EP-01-IMP-01] Refactor MQTT client for injectable dependencies
- **Summary**: Refactor MQTT client for injectable dependencies
- **Issue Type**: Task
- **Parent ID**: EP-01
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep01, implementation
- **Description**:
  - **Background**: To enable unit and integration tests, the MQTT client must support dependency injection for transport, timers, and metrics.
  - **In Scope**:
    - Extract interfaces for transport, logger, and metrics recorder.
    - Add configuration struct validated via .env loader.
    - Ensure reconnection and duplicate suppression logic rely on injected components to ease mocking.
  - **Out of Scope**:
    - Circuit breaker integration (EP-06).
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (MQTT client architecture)
- **Acceptance Criteria**:
  - [ ] New interfaces allow tests to stub transport and timers.
  - [ ] Configuration validation rejects missing endpoints or certs with actionable error.
  - [ ] Existing integration smoke test passes with new structure.

#### [TBD-EP-01-IMP-02] Implement connectivity watchdog metrics
- **Summary**: Implement connectivity watchdog metrics
- **Issue Type**: Task
- **Parent ID**: EP-01
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep01, implementation
- **Description**:
  - **Background**: Observability requirements call for watchdog timers and structured logs when connectivity drifts.
  - **In Scope**:
    - Emit Prometheus gauges for mqtt_connected and counters for reconnect attempts.
    - Add structured log entries with correlation id, broker url, and TLS fingerprint hash.
    - Wire metrics into existing monitoring registry from EP-08.
  - **Out of Scope**:
    - Alert definitions (documented in EP-08 tasks).
  - **References**:
    - docs/epics/EP-08 - Observability & Operational Readiness.md
- **Acceptance Criteria**:
  - [ ] Metrics appear in /metrics endpoint with documented names and labels.
  - [ ] Logs redact secrets and include context fields per logging spec.
  - [ ] Watchdog triggers recoveries during integration test scenario.

#### [TBD-EP-01-IMP-03] Update runbook for EMQX operations
- **Summary**: Update runbook for EMQX operations
- **Issue Type**: Task
- **Parent ID**: EP-01
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep01, documentation
- **Description**:
  - **Background**: Operational docs must capture new tests, metrics, and failure handling.
  - **In Scope**:
    - Document startup checklist, TLS certificate rotation steps, and retry tuning knobs.
    - Add troubleshooting matrix referencing new contract and integration tests.
    - Link to generated contract report and test fixtures.
  - **Out of Scope**:
    - Post-incident review templates.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Operations appendix)
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (OBS-02)
- **Acceptance Criteria**:
  - [ ] Runbook stored under docs/runbooks/emqx.md with table of failure modes vs actions.
  - [ ] References include latest test IDs and fixture locations.
  - [ ] Ops review sign-off recorded in project wiki.
