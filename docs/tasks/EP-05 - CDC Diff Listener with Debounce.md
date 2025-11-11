---
epic_id: EP-05
epic_title: CDC Diff Listener with Debounce
status: draft
last_updated: 2025-09-23
sources:
  - docs/epics/EP-05 - CDC Diff Listener with Debounce.md
  - docs/Metadata Sync Microservice Solution Design - Release 1.0.md
  - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md
jira_defaults:
  parent_id: EP-05
  issue_type: Task
  priority: High
  labels:
    - uns-meta
    - ep05
---

## Unit Tests

#### [TBD-EP-05-UT-01] Logical replication client unit tests
- **Summary**: Logical replication client unit tests
- **Issue Type**: Task
- **Parent ID**: EP-05
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep05, unit-test
- **Description**:
  - **Background**: CDC client must parse `pgoutput` messages and handle reconnects cleanly.
  - **In Scope**:
    - Mock replication stream delivering insert/update/delete combos.
    - Assert slot position tracking persists across reconnect scenarios.
    - Ensure error handling retries with exponential backoff and surfaces terminal failures.
  - **Out of Scope**:
    - Network integration with live Postgres.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-15)
- **Acceptance Criteria**:
  - [ ] Unit tests assert correct decoding of relation and column metadata.
  - [ ] Slot position checkpoints saved and restored accurately.
  - [ ] Backoff parameters conform to resiliency guidelines.

#### [TBD-EP-05-UT-02] Debounce buffer behavior tests
- **Summary**: Debounce buffer behavior tests
- **Issue Type**: Task
- **Parent ID**: EP-05
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep05, unit-test
- **Description**:
  - **Background**: Debounce logic must aggregate metric diffs within 3-minute window without memory leaks.
  - **In Scope**:
    - Cover add/update operations within window and ensure single emission.
    - Test buffer eviction after window expiry and on overload cap.
    - Validate metrics expose buffer depth and drops.
  - **Out of Scope**:
    - Actual Canary delivery.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-16)
- **Acceptance Criteria**:
  - [ ] Buffered events collapse into minimal diff payload after window.
  - [ ] Buffer cap triggers drop metrics and warning logs.
  - [ ] Memory footprint remains bounded in unit simulation.

#### [TBD-EP-05-UT-03] Diff computation integrity tests
- **Summary**: Diff computation integrity tests
- **Issue Type**: Task
- **Parent ID**: EP-05
- **Priority**: Medium
- **Story Points**: 2
- **Labels**: uns-meta, ep05, unit-test
- **Description**:
  - **Background**: Diff merger must respect order and include version metadata from EP-03/04 outputs.
  - **In Scope**:
    - Validate diff aggregator merges device and metric property changes correctly.
    - Ensure diff payload includes version numbers and actor metadata.
    - Confirm idempotent replays produce identical diff outputs.
  - **Out of Scope**:
    - Storage of diffs (handled by EP-04).
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (CDC diffing)
- **Acceptance Criteria**:
  - [ ] Unit tests compare generated diffs against golden snapshots.
  - [ ] Version ordering preserved for sequential updates.
  - [ ] Duplicate events yield no duplicate diff emissions.

## Integration Tests

#### [TBD-EP-05-IT-01] DB writes to CDC consumer pipeline test
- **Summary**: DB writes to CDC consumer pipeline test
- **Issue Type**: Task
- **Parent ID**: EP-05
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep05, integration-test
- **Description**:
  - **Background**: Validate real logical replication stream from Postgres to CDC consumer in dockerized environment.
  - **In Scope**:
    - Provision Postgres with publication `uns_meta_pub` and seed sample updates.
    - Connect CDC consumer and confirm diffs emitted to in-memory queue.
    - Measure latency and ensure within design targets (<10s post debounce).
  - **Out of Scope**:
    - Canary API integration.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (DI-04, TC-17)
- **Acceptance Criteria**:
  - [ ] Integration test spins up replication slot and processes events end-to-end.
  - [ ] Debounce window respected; metrics emitted for latency.
  - [ ] Pipeline resilient to transient disconnect (auto reconnect proven).

#### [TBD-EP-05-IT-02] Stress test debounce under burst load
- **Summary**: Stress test debounce under burst load
- **Issue Type**: Task
- **Parent ID**: EP-05
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep05, integration-test
- **Description**:
  - **Background**: Need assurance debounce window handles high-frequency updates without backlog.
  - **In Scope**:
    - Replay synthetic workload with 1k updates per minute on single metric.
    - Confirm throughput and memory metrics meet targets.
    - Capture CPU usage and provide tuning recommendations.
  - **Out of Scope**:
    - Canary throughput tests.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Performance goals)
- **Acceptance Criteria**:
  - [ ] Stress run completes without OOM and within acceptable latency.
  - [ ] Metrics confirm buffer cap not exceeded under configured load.
  - [ ] Report generated with tuning guidance.

## Contract Tests

#### [TBD-EP-05-CT-01] CDC diff payload contract
- **Summary**: CDC diff payload contract
- **Issue Type**: Task
- **Parent ID**: EP-05
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep05, contract-test
- **Description**:
  - **Background**: Downstream Canary integration requires stable diff schema.
  - **In Scope**:
    - Define JSON schema for diff payload including debounce metadata.
    - Validate integration tests emit payload matching schema.
    - Publish schema for consumers and version it.
  - **Out of Scope**:
    - Canary-specific fields beyond diff.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-17)
- **Acceptance Criteria**:
  - [ ] Contract tests fail on schema drift.
  - [ ] Schema stored under `docs/contracts/cdc_diff.json` with changelog.
  - [ ] Communication sent to Canary team about schema availability.

## Implementation

#### [TBD-EP-05-IMP-01] Build CDC listener service
- **Summary**: Build CDC listener service
- **Issue Type**: Task
- **Parent ID**: EP-05
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep05, implementation
- **Description**:
  - **Background**: Implement production service that connects to replication slot and emits debounced diffs.
  - **In Scope**:
    - Implement replication connection management, slot creation, and heartbeats.
    - Integrate debounce buffer and diff generator.
    - Expose metrics for lag, buffer depth, and error counts.
  - **Out of Scope**:
    - Canary delivery.
  - **References**:
    - docs/epics/EP-05 - CDC Diff Listener with Debounce.md
- **Acceptance Criteria**:
  - [ ] Service handles reconnects without losing position.
  - [ ] Metrics appear in observability stack with documented names.
  - [ ] Integration tests pass end-to-end.

#### [TBD-EP-05-IMP-02] Implement persistence for resume tokens
- **Summary**: Implement persistence for resume tokens
- **Issue Type**: Task
- **Parent ID**: EP-05
- **Priority**: Medium
- **Story Points**: 2
- **Labels**: uns-meta, ep05, implementation
- **Description**:
  - **Background**: Resume tokens ensure CDC restarts continue without duplication.
  - **In Scope**:
    - Store slot positions in durable store with atomic updates.
    - Provide API for manual reset with safeguards.
    - Add smoke test verifying resume after restart.
  - **Out of Scope**:
    - Multi-instance coordination.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (CDC resiliency)
- **Acceptance Criteria**:
  - [ ] Resume tokens persist across restarts and remain consistent.
  - [ ] Manual reset endpoint documented and secured.
  - [ ] Smoke test demonstrates restart reliability.

#### [TBD-EP-05-IMP-03] Debounce configuration documentation
- **Summary**: Debounce configuration documentation
- **Issue Type**: Task
- **Parent ID**: EP-05
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep05, documentation
- **Description**:
  - **Background**: Operators need clarity on tuning debounce window and buffer caps.
  - **In Scope**:
    - Document configuration parameters, defaults, and recommended values.
    - Provide troubleshooting guidance for lag or backlog scenarios.
    - Reference metrics and alert thresholds.
  - **Out of Scope**:
    - Full SRE runbook for Canary integration.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Operations)
- **Acceptance Criteria**:
  - [ ] Documentation stored at `docs/runbooks/cdc-debounce.md`.
  - [ ] Includes table of configs vs symptoms.
  - [ ] Reviewed by ops lead.
