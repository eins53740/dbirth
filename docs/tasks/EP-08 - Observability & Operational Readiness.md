---
epic_id: EP-08
epic_title: Observability & Operational Readiness
status: draft
last_updated: 2025-09-23
sources:
  - docs/epics/EP-08 - Observability & Operational Readiness.md
  - docs/Metadata Sync Microservice Solution Design - Release 1.0.md
  - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md
jira_defaults:
  parent_id: EP-08
  issue_type: Task
  priority: High
  labels:
    - uns-meta
    - ep08
---

## Unit Tests

#### [TBD-EP-08-UT-01] Metrics registry coverage
- **Summary**: Metrics registry coverage
- **Issue Type**: Task
- **Parent ID**: EP-08
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep08, unit-test
- **Description**:
  - **Background**: Metrics registry should expose counters, gauges, histograms for all critical workflows.
  - **In Scope**:
    - Unit tests verifying registration of metrics defined in observability spec.
    - Ensure metric names and labels follow naming convention.
    - Validate lazy initialization avoids duplicate registrations.
  - **Out of Scope**:
    - Exporter integration (covered in integration tests).
  - **References**:
    - docs/epics/EP-08 - Observability & Operational Readiness.md
- **Acceptance Criteria**:
  - [ ] Unit tests confirm presence of ingest, decode, db, cdc, canary metrics.
  - [ ] Label sets validated against spec to prevent cardinality explosion.
  - [ ] Duplicate registration attempts raise errors caught by tests.

#### [TBD-EP-08-UT-02] Structured logging formatter tests
- **Summary**: Structured logging formatter tests
- **Issue Type**: Task
- **Parent ID**: EP-08
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep08, unit-test
- **Description**:
  - **Background**: Logging formatter must produce JSON with correlation ids and redaction.
  - **In Scope**:
    - Tests for log fields, timestamp formatting, level mapping.
    - Validate redaction of sensitive fields works with nested objects.
    - Ensure error stack traces captured in structured fields.
  - **Out of Scope**:
    - External log shipping.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (OBS-02)
- **Acceptance Criteria**:
  - [ ] Logs render as JSON with required fields present.
  - [ ] Redaction covers configured keys and patterns.
  - [ ] Formatter handles errors without panics.

#### [TBD-EP-08-UT-03] Alert rule unit validation
- **Summary**: Alert rule unit validation
- **Issue Type**: Task
- **Parent ID**: EP-08
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep08, unit-test
- **Description**:
  - **Background**: Ensure Prometheus alert rule templates render correctly with placeholder data.
  - **In Scope**:
    - Use promtool or similar to validate syntax.
    - Provide sample data to ensure alert triggers as expected.
    - Cover alerts for CDC lag, circuit open, and sustained failures.
  - **Out of Scope**:
    - Pagerduty integration.
  - **References**:
    - docs/epics/EP-08 - Observability & Operational Readiness.md
- **Acceptance Criteria**:
  - [ ] promtool validation passes for all recording/alerting rules.
  - [ ] Unit tests confirm alert expression thresholds align with runbook guidance.
  - [ ] Template variables resolved without missing values.

## Integration Tests

#### [TBD-EP-08-IT-01] Prometheus scrape integration test
- **Summary**: Prometheus scrape integration test
- **Issue Type**: Task
- **Parent ID**: EP-08
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep08, integration-test
- **Description**:
  - **Background**: Validate metrics endpoint exposes expected metrics and responds within latency budget.
  - **In Scope**:
    - Spin up service with instrumentation enabled.
    - Use Prometheus docker container to scrape and verify metric presence.
    - Check performance overhead remains within <10ms per scrape.
  - **Out of Scope**:
    - Long-term retention config.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (OBS-01)
- **Acceptance Criteria**:
  - [ ] Integration test confirms metrics appear with expected values after workload.
  - [ ] Scrape latency under threshold measured.
  - [ ] CI publishes scrape verification report.

#### [TBD-EP-08-IT-02] Log pipeline integration test
- **Summary**: Log pipeline integration test
- **Issue Type**: Task
- **Parent ID**: EP-08
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep08, integration-test
- **Description**:
  - **Background**: Ensure logs can be shipped to aggregation stack and maintain structure.
  - **In Scope**:
    - Send sample workloads generating error/info logs.
    - Push logs through Fluent Bit or vector to local sink.
    - Verify structure preserved and secrets redacted.
  - **Out of Scope**:
    - Production log platform integration.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Logging)
- **Acceptance Criteria**:
  - [ ] Aggregated logs remain JSON and searchable by correlation id.
  - [ ] Redactions confirmed in downstream sink.
  - [ ] Documentation updated with pipeline steps.

## Contract Tests

#### [TBD-EP-08-CT-01] Observability contract catalogue
- **Summary**: Observability contract catalogue
- **Issue Type**: Task
- **Parent ID**: EP-08
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep08, contract-test
- **Description**:
  - **Background**: Provide formal catalogue of metrics, logs, and alerts for stakeholders.
  - **In Scope**:
    - Generate markdown table listing metric names, descriptions, labels, owners.
    - Include JSON schema for log events.
    - Link alert definitions with severity and runbook references.
  - **Out of Scope**:
    - Dashboard definitions.
  - **References**:
    - docs/epics/EP-08 - Observability & Operational Readiness.md
- **Acceptance Criteria**:
  - [ ] Catalogue stored at `docs/contracts/observability_catalog.md`.
  - [ ] CI check ensures catalogue updated when instrumentation changes.
  - [ ] Stakeholders acknowledge receipt.

## Implementation

#### [TBD-EP-08-IMP-01] Implement Prometheus instrumentation
- **Summary**: Implement Prometheus instrumentation
- **Issue Type**: Task
- **Parent ID**: EP-08
- **Priority**: High
- **Story Points**: 4
- **Labels**: uns-meta, ep08, implementation
- **Description**:
  - **Background**: Add instrumentation within services for ingest, decode, persistence, CDC, and Canary flows.
  - **In Scope**:
    - Register counters/gauges/histograms per spec.
    - Integrate metrics emission in critical code paths.
    - Document metric naming and label usage inline.
  - **Out of Scope**:
    - External alerting config.
  - **References**:
    - docs/epics/EP-08 - Observability & Operational Readiness.md
- **Acceptance Criteria**:
  - [ ] Metrics available via `/metrics` endpoint.
  - [ ] Unit/integration tests confirm instrumentation.
  - [ ] Performance impact measured and acceptable.

#### [TBD-EP-08-IMP-02] Implement structured logging stack
- **Summary**: Implement structured logging stack
- **Issue Type**: Task
- **Parent ID**: EP-08
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep08, implementation
- **Description**:
  - **Background**: Provide JSON logging with correlation ids and redaction.
  - **In Scope**:
    - Configure logging library with context propagation.
    - Integrate request/metric ids to logs.
    - Ensure error handling logs include stack traces.
  - **Out of Scope**:
    - Log storage infrastructure.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Logging)
- **Acceptance Criteria**:
  - [ ] Logs match structured format across services.
  - [ ] Tests confirm redaction rules applied.
  - [ ] Observability doc references log structure.

#### [TBD-EP-08-IMP-03] Draft alerting runbook
- **Summary**: Draft alerting runbook
- **Issue Type**: Task
- **Parent ID**: EP-08
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep08, documentation
- **Description**:
  - **Background**: Operators require guide linking alerts to actions.
  - **In Scope**:
    - Document alerts, thresholds, escalation contacts.
    - Provide troubleshooting steps per alert.
    - Link to metrics/logging resources.
  - **Out of Scope**:
    - Incident management policy.
  - **References**:
    - docs/epics/EP-08 - Observability & Operational Readiness.md
- **Acceptance Criteria**:
  - [ ] Runbook stored at `docs/runbooks/alerting.md`.
  - [ ] Includes mapping of alert -> metric -> remediation.
  - [ ] Reviewed by SRE team.
