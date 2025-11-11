---
epic_id: EP-03
epic_title: UNS Path Normalization & Identity Model
status: draft
last_updated: 2025-09-23
sources:
  - docs/epics/EP-03 - UNS Path Normalization & Identity Model.md
  - docs/Metadata Sync Microservice Solution Design - Release 1.0.md
  - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.0).md
  - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md
jira_defaults:
  parent_id: EP-03
  issue_type: Task
  priority: High
  labels:
    - uns-meta
    - ep03
---

## Unit Tests

#### [TBD-EP-03-UT-01] Canonical UNS path normalization tests
- **Summary**: Canonical UNS path normalization tests
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep03, unit-test
- **Description**:
  - **Background**: Path normalizer must transform topics and decoded payload context into deterministic device and metric UNS paths.
  - **In Scope**:
    - Add table-driven unit tests covering hierarchy variations, missing segments, and illegal characters.
    - Assert casing normalization, whitespace trimming, and delimiter replacement follow convention.
    - Validate uns_path results interface correctly with canary id generator.
  - **Out of Scope**:
    - Database persistence of paths (covered by EP-04).
  - **References**:
    - docs/epics/EP-03 - UNS Path Normalization & Identity Model.md
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-02)
- **Acceptance Criteria**:
  - [ ] Unit suite covers happy path, missing hierarchy, invalid characters, and overrides.
  - [ ] Normalizer output matches golden UNS path fixtures stored under ixtures/uns/paths.
  - [ ] Failures highlight segment-level diff for debugging.

#### [TBD-EP-03-UT-02] Identity collision detection tests
- **Summary**: Identity collision detection tests
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep03, unit-test
- **Description**:
  - **Background**: Need assurance that distinct inputs never collide to same UNS path or canary id unexpectedly.
  - **In Scope**:
    - Generate fuzzed topics/metrics to confirm unique uns_path values per combination.
    - Validate collision detector raises errors when normalization would result in duplicate keys.
    - Ensure canonicalization handles international characters by fallback escaping.
  - **Out of Scope**:
    - Storage layer conflict handling (EP-04).
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (DI-02)
- **Acceptance Criteria**:
  - [ ] Fuzz test runs 10k iterations without collision; collisions raise explicit error message.
  - [ ] Escaping logic produces deterministic replacements for non-ASCII while staying ASCII-only.
  - [ ] canary_id generation mirrors uns_path segments with dot delimiter.

#### [TBD-EP-03-UT-03] Idempotent upsert decision logic tests
- **Summary**: Idempotent upsert decision logic tests
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep03, unit-test
- **Description**:
  - **Background**: Upsert planner functions compare normalized identities to persisted snapshots; need deterministic outcomes.
  - **In Scope**:
    - Cover scenarios for insert, update, noop decisions based on uns_path and property diffs.
    - Confirm lineage handoff payload includes previous path when updates triggered.
    - Assert planner remains idempotent when invoked repeatedly with same input.
  - **Out of Scope**:
    - Physical DB writes (EP-04) and CDC emission (EP-05).
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Identity persistence)
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-03)
- **Acceptance Criteria**:
  - [ ] Decision outputs match expected action enumerations across fixtures.
  - [ ] Path rename ensures lineage payload contains previous and new paths.
  - [ ] Re-running planner with identical inputs yields noop decision consistently.

#### [TBD-EP-03-UT-04] Diff computation coverage for identity changes
- **Summary**: Diff computation coverage for identity changes
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: Medium
- **Story Points**: 2
- **Labels**: uns-meta, ep03, unit-test
- **Description**:
  - **Background**: Diff generator feeds EP-04 version history; must capture segment-level changes accurately.
  - **In Scope**:
    - Unit tests verifying diff outputs for segment additions, removals, and property updates.
    - Confirm diff payload includes metadata for CDC consumption (timestamp, actor).
    - Ensure empty diffs returned when only non-material fields change.
  - **Out of Scope**:
    - CDC transmission wiring (EP-05).
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-07)
- **Acceptance Criteria**:
  - [ ] Diff output structured as documented JSON schema with before/after segments.
  - [ ] Property changes capture old/new values with type metadata.
  - [ ] No diff entries produced for unchanged inputs.

#### [TBD-EP-03-UT-05] Retry helper coverage for identity persistence
- **Summary**: Retry helper coverage for identity persistence
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep03, unit-test
- **Description**:
  - **Background**: Identity persistence consumes retry/backoff helpers shared with EP-01; need targeted tests around identity-specific side effects.
  - **In Scope**:
    - Validate retries wrap planner execution without duplicating lineage events.
    - Ensure jitter/backoff config aligns with EP-04 transaction expectations.
    - Confirm metrics record failure counts labeled by identity segment.
  - **Out of Scope**:
    - Transport-level retries (handled elsewhere).
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Resiliency)
- **Acceptance Criteria**:
  - [ ] Tests assert no duplicate lineage events emitted during retries.
  - [ ] Backoff schedule remains under 30s aggregate per design.
  - [ ] Metrics instrumentation validated via test harness.

## Integration Tests

#### [TBD-EP-03-IT-01] Normalized path persistence with Postgres
- **Summary**: Normalized path persistence with Postgres
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep03, integration-test
- **Description**:
  - **Background**: Integration scenario ensures normalized paths flow from MQTT ingest through decoder into Postgres tables.
  - **In Scope**:
    - Combine EP-01 ingest harness and EP-02 decoder to persist rows.
    - Verify uns_path and canary_id columns populated correctly for devices and metrics.
    - Execute re-ingest after rename to ensure lineage staging updated.
  - **Out of Scope**:
    - CDC or Canary delivery.
  - **References**:
    - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.0).md (devices, metrics tables)
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (DI-02)
- **Acceptance Criteria**:
  - [ ] Integration run writes expected rows with deterministic uns_path/canary_id.
  - [ ] Path rename scenario updates existing row and writes lineage entry.
  - [ ] Idempotent replays produce no duplicate rows.

#### [TBD-EP-03-IT-02] Identity diff handoff to CDC staging
- **Summary**: Identity diff handoff to CDC staging
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep03, integration-test
- **Description**:
  - **Background**: Need to confirm diff generator output flows into staging tables consumed by EP-05.
  - **In Scope**:
    - Run identity change scenarios and ensure diff JSON stored in staging schema.
    - Validate ordering semantics for sequential changes on same metric.
    - Compare diff payload with expected golden JSON for CDC.
  - **Out of Scope**:
    - Actual replication slot processing.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (Diff pipeline)
- **Acceptance Criteria**:
  - [ ] Staging tables contain diff payloads matching contract schema.
  - [ ] Sequence numbers monotonic per metric.
  - [ ] Golden diff comparison passes for sample fixtures.

## Contract Tests

#### [TBD-EP-03-CT-01] UNS path formatting contract
- **Summary**: UNS path formatting contract
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep03, contract-test
- **Description**:
  - **Background**: Establish documented contract for UNS path grammar to coordinate across teams.
  - **In Scope**:
    - Define JSON schema representing segment list, allowed characters, and required fields.
    - Add contract tests to validate normalizer output against schema.
    - Publish contract doc for consumers including Canary integration team.
  - **Out of Scope**:
    - Business-specific naming override negotiations.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md (UNS naming)
- **Acceptance Criteria**:
  - [ ] Contract tests fail when new segment introduced without schema update.
  - [ ] Schema documented under docs/contracts/uns_path.json with commentary.
  - [ ] Canary integration team sign-off captured.

## Implementation

#### [TBD-EP-03-IMP-01] Implement UNS normalizer module
- **Summary**: Implement UNS normalizer module
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep03, implementation
- **Description**:
  - **Background**: Need production-ready normalizer with clear interfaces for decoder and persistence layers.
  - **In Scope**:
    - Build module exposing deterministic device/metric normalization functions.
    - Include validation utilities returning structured errors with segment context.
    - Provide configuration hooks for plant-specific overrides.
  - **Out of Scope**:
    - Cross-plant reconciliation.
  - **References**:
    - docs/epics/EP-03 - UNS Path Normalization & Identity Model.md
- **Acceptance Criteria**:
  - [ ] Module consumed by decoder and persistence without circular dependencies.
  - [ ] Validation errors map to HTTP 4xx codes for API consumers (when applicable).
  - [ ] Benchmarks show normalization under 5ms per metric.

#### [TBD-EP-03-IMP-02] Generate canary_id derivation utility
- **Summary**: Generate canary_id derivation utility
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: Medium
- **Story Points**: 2
- **Labels**: uns-meta, ep03, implementation
- **Description**:
  - **Background**: canary_id needs standalone helper to maintain consistent transformation logic.
  - **In Scope**:
    - Implement transformation from uns_path to dot-delimited identifier with escape rules.
    - Include checksum option for future extension.
    - Provide unit-level metrics for collisions.
  - **Out of Scope**:
    - Canary API invocation.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (DI-02)
- **Acceptance Criteria**:
  - [ ] Helper passes all unit tests and returns deterministic IDs.
  - [ ] Escaping rules documented and logged when triggered.
  - [ ] Collision counter increments when duplicates attempted.

#### [TBD-EP-03-IMP-03] Document identity model lifecycle
- **Summary**: Document identity model lifecycle
- **Issue Type**: Task
- **Parent ID**: EP-03
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep03, documentation
- **Description**:
  - **Background**: Provide cohesive documentation across ingest, normalization, persistence, and CDC for identities.
  - **In Scope**:
    - Author markdown doc describing flow with sequence diagram.
    - Link to tests, schema, and contract artifacts.
    - Add troubleshooting cheatsheet for path conflicts.
  - **Out of Scope**:
    - Canary-specific mapping details (EP-06).
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.0.md
- **Acceptance Criteria**:
  - [ ] Doc stored under docs/runbooks/identity-lifecycle.md.
  - [ ] Sequence diagram checked into docs/diagrams with source file.
  - [ ] Reviewed by data governance lead.
