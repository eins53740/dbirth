---
epic_id: EP-02
epic_title: Payload Decode & Alias Resolution
status: draft
last_updated: 2025-09-23
sources:
  - docs/epics/EP-02 - Payload Decode & Alias Resolution.md
  - docs/Metadata Sync Microservice Solution Design - Release 1.0.md
  - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md
jira_defaults:
  parent_id: EP-02
  issue_type: Task
  priority: High
  labels:
    - uns-meta
    - ep02
---

## Unit Tests

#### [TBD-EP-02-UT-01] Expand Sparkplug payload decode fixture coverage
- **Summary**: Expand Sparkplug payload decode fixture coverage
- **Issue Type**: Task
- **Parent ID**: EP-02
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep02, unit-test
- **Description**:
  - **Background**: Payload decoder must support metrics, dataset values, and property sets per Sparkplug B spec with regression coverage for new fixture variants.
  - **In Scope**:
    - Add binary and JSON fixtures for int64, float, boolean, string, and dataset metrics.
    - Verify decoder preserves property metadata including timestamps and flags.
    - Assert errors include alias and metric metadata for troubleshooting.
  - **Out of Scope**:
    - State support for complex dataset operations beyond read-only decode.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-01, TC-04)
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Payload decode)
- **Acceptance Criteria**:
  - [ ] Unit tests decode all fixture types without data loss or type mismatch.
  - [ ] Decoder raises descriptive errors for unsupported datatypes with metric context.
  - [ ] Fixtures stored under ixtures/sparkplug/dbirth with README.

#### [TBD-EP-02-UT-02] Alias cache lookup precedence tests
- **Summary**: Alias cache lookup precedence tests
- **Issue Type**: Task
- **Parent ID**: EP-02
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep02, unit-test
- **Description**:
  - **Background**: Alias cache currently assumes device-level map precedence; tests must enforce fallback behavior.
  - **In Scope**:
    - Cover lookups with device -> node fallback and fallback to lias:<id>.
    - Validate cache persistence events triggered on DBIRTH vs control messages.
    - Ensure REBIRTH throttle increments metrics when alias missing.
  - **Out of Scope**:
    - Cache invalidation triggered by CDC diffs (EP-05).
  - **References**:
    - docs/epics/EP-02 - Payload Decode & Alias Resolution.md
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-05)
- **Acceptance Criteria**:
  - [ ] Tests assert device alias overrides node alias.
  - [ ] Missing alias produces lias:<id> naming without throwing.
  - [ ] Throttle metrics increment per REBIRTH request issued.

#### [TBD-EP-02-UT-03] Property typing validation for decoded metrics
- **Summary**: Property typing validation for decoded metrics
- **Issue Type**: Task
- **Parent ID**: EP-02
- **Priority**: Medium
- **Story Points**: 2
- **Labels**: uns-meta, ep02, unit-test
- **Description**:
  - **Background**: Property typing rules defined in schema doc require automated verification to avoid downstream persistence errors.
  - **In Scope**:
    - Tests for numeric range enforcement, string length normalization, and UTF-8 sanitizer.
    - Confirm property map retains units, scale, and metadata flags documented in schema.
    - Ensure typed properties integrate with identity normalizer (EP-03) without mutation.
  - **Out of Scope**:
    - Database persistence (covered in EP-04 integration tests).
  - **References**:
    - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.0).md (metric_properties)
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-04)
- **Acceptance Criteria**:
  - [ ] Invalid properties raise structured validation errors referencing offending key.
  - [ ] Sanitized strings remain within length bounds and preserve significant characters.
  - [ ] Unit tests prove compatibility with UNS path normalizer API surface.

## Integration Tests

#### [TBD-EP-02-IT-01] Alias resolution end-to-end with MQTT ingest
- **Summary**: Alias resolution end-to-end with MQTT ingest
- **Issue Type**: Task
- **Parent ID**: EP-02
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep02, integration-test
- **Description**:
  - **Background**: Need integration coverage to ensure decoded metrics map to canonical names when driven by MQTT ingest harness from EP-01.
  - **In Scope**:
    - Reuse EMQX integration rig; inject fixtures with alias/per metric combos.
    - Confirm alias cache persists to local store and reloads on service restart.
    - Validate unresolved aliases trigger REBIRTH publisher with throttle guard.
  - **Out of Scope**:
    - Postgres write validation (asserted separately in EP-04 tests).
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-05)
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Alias resolution)
- **Acceptance Criteria**:
  - [ ] Integration run produces deterministic metric names across restarts.
  - [ ] REBIRTH throttle prevents duplicate requests within configured window.
  - [ ] Alias persistence verified via cache file/hash snapshot.

#### [TBD-EP-02-IT-02] Decoder regression across versioned fixtures
- **Summary**: Decoder regression across versioned fixtures
- **Issue Type**: Task
- **Parent ID**: EP-02
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep02, integration-test
- **Description**:
  - **Background**: Need harness to run multiple historical DBIRTH fixture versions ensuring backward compatibility.
  - **In Scope**:
    - Organize fixture catalog by plant/device release.
    - Run decode pipeline and assert property schema upgrades convert correctly.
    - Capture golden JSON outputs for diffing in CI.
  - **Out of Scope**:
    - Canary API integration.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Fixture strategy)
- **Acceptance Criteria**:
  - [ ] Versioned fixtures produce expected normalized JSON snapshots.
  - [ ] Regression harness fails when decoder output deviates from golden snapshots.
  - [ ] CI job publishes diff artifact for review.

## Contract Tests

#### [TBD-EP-02-CT-01] Sparkplug payload contract verification
- **Summary**: Sparkplug payload contract verification
- **Issue Type**: Task
- **Parent ID**: EP-02
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep02, contract-test
- **Description**:
  - **Background**: Establish formal contract tests verifying decoder compatibility with Sparkplug B spec sections used by project.
  - **In Scope**:
    - Encode and decode using reference protobuf definitions, asserting round-trip fidelity.
    - Validate metric alias, datatype, and property structures from sample edge devices.
    - Document unsupported features with clear backlog follow-ups.
  - **Out of Scope**:
    - Broker-specific transport considerations.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-01)
- **Acceptance Criteria**:
  - [ ] Contract test suite fails on protobuf schema drift or unsupported datatype introduction.
  - [ ] Output report stored under docs/contracts/sparkplug_payload.md summarizing coverage.
  - [ ] Known limitations documented with Jira follow-up links.

## Implementation

#### [TBD-EP-02-IMP-01] Modularize payload decoder components
- **Summary**: Modularize payload decoder components
- **Issue Type**: Task
- **Parent ID**: EP-02
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep02, implementation
- **Description**:
  - **Background**: Decoder currently monolithic; needs separation for metrics, properties, and alias management for testability.
  - **In Scope**:
    - Split decoder into metric extractor, property parser, alias resolver modules.
    - Provide clear interfaces for injecting fixtures and mocks.
    - Ensure modules publish structured errors for observability integration.
  - **Out of Scope**:
    - Database persistence logic.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Decoder architecture)
- **Acceptance Criteria**:
  - [ ] Modules expose interfaces consumed by unit/integration tests.
  - [ ] Error objects include alias, metric name, device context.
  - [ ] Existing functionality preserved per regression suite.

#### [TBD-EP-02-IMP-02] Implement alias cache persistence layer
- **Summary**: Implement alias cache persistence layer
- **Issue Type**: Task
- **Parent ID**: EP-02
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep02, implementation
- **Description**:
  - **Background**: Alias cache should persist across restarts using lightweight storage with TTL controls.
  - **In Scope**:
    - Choose storage mechanism (sqlite/json) with write-through semantics.
    - Add TTL and cleanup routine per design doc.
    - Expose metrics for cache hit ratio.
  - **Out of Scope**:
    - Distributed cache synchronization.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Alias cache)
- **Acceptance Criteria**:
  - [ ] Cache persists between service restarts in local dev environment.
  - [ ] TTL eviction removes stale entries per configured window.
  - [ ] Metrics include cache hit/miss counters.

#### [TBD-EP-02-IMP-03] Document alias resolution workflow
- **Summary**: Document alias resolution workflow
- **Issue Type**: Task
- **Parent ID**: EP-02
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep02, documentation
- **Description**:
  - **Background**: Need clarity for operations and developers on alias resolution lifecycle.
  - **In Scope**:
    - Create sequence diagram showing decode -> cache lookup -> REBIRTH.
    - Document configuration flags, throttle settings, and troubleshooting tips.
    - Link to fixtures and tests introduced in this epic.
  - **Out of Scope**:
    - Business-level alias governance.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Appendix)
- **Acceptance Criteria**:
  - [ ] Documentation stored under docs/runbooks/alias-resolution.md with diagrams.
  - [ ] Includes mapping of test IDs to features.
  - [ ] Reviewed by product trio with sign-off notes.
