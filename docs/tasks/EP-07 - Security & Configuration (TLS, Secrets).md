---
epic_id: EP-07
epic_title: Security & Configuration (TLS, Secrets)
status: draft
last_updated: 2025-09-23
sources:
  - docs/epics/EP-07 - Security & Configuration (TLS, Secrets).md
  - docs/Metadata Sync Microservice Solution Design - Release 1.0.md
  - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md
jira_defaults:
  parent_id: EP-07
  issue_type: Task
  priority: High
  labels:
    - uns-meta
    - ep07
---

## Unit Tests

#### [TBD-EP-07-UT-01] Configuration loader validation tests
- **Summary**: Configuration loader validation tests
- **Issue Type**: Task
- **Parent ID**: EP-07
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep07, unit-test
- **Description**:
  - **Background**: Config loader must enforce required env vars, defaults, and secret masking.
  - **In Scope**:
    - Tests covering missing env vars, invalid formats, and fallback defaults.
    - Ensure secrets flagged for masking never appear in error strings.
    - Validate config snapshot exported for observability excludes sensitive fields.
  - **Out of Scope**:
    - Dynamic reload (EP-01 covers for MQTT credentials).
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (SEC-02)
- **Acceptance Criteria**:
  - [ ] Loader raises descriptive errors for missing/invalid configs.
  - [ ] Snapshot redacts secrets while retaining non-sensitive fields.
  - [ ] Unit tests cover both success and failure paths.

#### [TBD-EP-07-UT-02] TLS trust store and certificate management tests
- **Summary**: TLS trust store and certificate management tests
- **Issue Type**: Task
- **Parent ID**: EP-07
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep07, unit-test
- **Description**:
  - **Background**: TLS helper must load trust stores, validate cert expiration, and enforce TLS 1.3.
  - **In Scope**:
    - Mock trust store loading with rotated certs.
    - Assert helper rejects expired or mismatched host certs.
    - Verify cipher suites limited to approved list.
  - **Out of Scope**:
    - mTLS client certificates.
  - **References**:
    - docs/epics/EP-07 - Security & Configuration (TLS, Secrets).md
- **Acceptance Criteria**:
  - [ ] Tests fail if TLS version lower than 1.3 permitted.
  - [ ] Expired or mismatched certificates raise actionable errors.
  - [ ] Metrics/logging capture rotation events without secrets.

#### [TBD-EP-07-UT-03] Secret handling regression tests
- **Summary**: Secret handling regression tests
- **Issue Type**: Task
- **Parent ID**: EP-07
- **Priority**: Medium
- **Story Points**: 2
- **Labels**: uns-meta, ep07, unit-test
- **Description**:
  - **Background**: Need to ensure secrets never leak to logs or panic traces.
  - **In Scope**:
    - Introduce fuzz tests to ensure logging sanitizer removes sensitive patterns.
    - Validate panic handler scrubs secrets before writing crash dumps.
    - Confirm metrics avoid labeling with secret values.
  - **Out of Scope**:
    - External log aggregation.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (SEC-03)
- **Acceptance Criteria**:
  - [ ] Log output and crash reports contain redacted placeholders.
  - [ ] sanitizer handles unicode and binary secrets without failure.
  - [ ] Tests trigger warnings if new logging paths bypass sanitizer.

## Integration Tests

#### [TBD-EP-07-IT-01] TLS end-to-end verification for EMQX and Postgres
- **Summary**: TLS end-to-end verification for EMQX and Postgres
- **Issue Type**: Task
- **Parent ID**: EP-07
- **Priority**: High
- **Story Points**: 4
- **Labels**: uns-meta, ep07, integration-test
- **Description**:
  - **Background**: Validate service enforces TLS connections to both EMQX and Postgres in a realistic environment.
  - **In Scope**:
    - Launch docker compose with EMQX and Postgres using TLS certs.
    - Confirm clients reject self-signed certs unless trust override set.
    - Capture observability metrics/logs for handshake success/failure.
  - **Out of Scope**:
    - Canary TLS integration.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (SEC-01)
- **Acceptance Criteria**:
  - [ ] Integration fails when TLS disabled, succeeding when enabled with proper trust.
  - [ ] Logs/metrics capture handshake outcomes.
  - [ ] CI job runs integration test in nightly pipeline.

#### [TBD-EP-07-IT-02] Permission boundary integration test
- **Summary**: Permission boundary integration test
- **Issue Type**: Task
- **Parent ID**: EP-07
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep07, integration-test
- **Description**:
  - **Background**: Ensure database users `uns_meta_app` and `uns_meta_cdc` have least privilege.
  - **In Scope**:
    - Attempt restricted operations (DDL, admin functions) and confirm denied.
    - Verify necessary permissions (select/insert/update) function.
    - Document results for audit.
  - **Out of Scope**:
    - Broader RBAC review.
  - **References**:
    - docs/epics/EP-07 - Security & Configuration (TLS, Secrets).md
- **Acceptance Criteria**:
  - [ ] Unauthorized operations fail with permission errors.
  - [ ] Authorized operations succeed for normal workflow.
  - [ ] Audit log stored in `docs/reports/db-permissions.md`.

## Contract Tests

#### [TBD-EP-07-CT-01] Security posture contract report
- **Summary**: Security posture contract report
- **Issue Type**: Task
- **Parent ID**: EP-07
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep07, contract-test
- **Description**:
  - **Background**: Provide consumable report enumerating required TLS versions, cipher suites, and secret storage expectations.
  - **In Scope**:
    - Generate markdown report from automated checks.
    - Version the report and track approval in security wiki.
    - Include checklist referencing SEC test cases.
  - **Out of Scope**:
    - Penetration testing results.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (SEC-01/02/03)
- **Acceptance Criteria**:
  - [ ] Report generated automatically and stored at `docs/contracts/security_posture.md`.
  - [ ] Any deviation from approved configuration fails CI.
  - [ ] Security lead sign-off recorded.

## Implementation

#### [TBD-EP-07-IMP-01] Harden configuration management module
- **Summary**: Harden configuration management module
- **Issue Type**: Task
- **Parent ID**: EP-07
- **Priority**: High
- **Story Points**: 4
- **Labels**: uns-meta, ep07, implementation
- **Description**:
  - **Background**: Need robust config loader with validation, defaults, and secret masking.
  - **In Scope**:
    - Implement typed config structs with validation methods.
    - Integrate with vault or env sourcing as defined.
    - Provide runtime reload hooks where needed.
  - **Out of Scope**:
    - UI for config edits.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Configuration)
- **Acceptance Criteria**:
  - [ ] Module passes unit/integration tests and plugs into services.
  - [ ] Secrets masked in logs and metrics.
  - [ ] Invalid config prevents startup with clear error.

#### [TBD-EP-07-IMP-02] Implement TLS asset management
- **Summary**: Implement TLS asset management
- **Issue Type**: Task
- **Parent ID**: EP-07
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep07, implementation
- **Description**:
  - **Background**: Manage certificates and trust stores for MQTT and Postgres clients.
  - **In Scope**:
    - Provide utility to load certs from disk or secret store.
    - Implement rotation watcher with safe reload.
    - Emit metrics/logging on rotation events.
  - **Out of Scope**:
    - Server-side certificate issuance.
  - **References**:
    - docs/epics/EP-07 - Security & Configuration (TLS, Secrets).md
- **Acceptance Criteria**:
  - [ ] Cert rotations occur without downtime in staging test.
  - [ ] Metrics/logs capture rotation success/failure.
  - [ ] Documentation updated with rotation steps.

#### [TBD-EP-07-IMP-03] Security checklist documentation
- **Summary**: Security checklist documentation
- **Issue Type**: Task
- **Parent ID**: EP-07
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep07, documentation
- **Description**:
  - **Background**: Provide go-live checklist covering TLS, secrets, and permissions.
  - **In Scope**:
    - Draft checklist referencing tests and automation.
    - Include escalation contacts and review cadence.
    - Store under security docs with versioning.
  - **Out of Scope**:
    - Broader corporate security policies.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (Security section)
- **Acceptance Criteria**:
  - [ ] Checklist stored at `docs/runbooks/security-checklist.md`.
  - [ ] Includes mapping to SEC test cases.
  - [ ] Approved by security lead.
