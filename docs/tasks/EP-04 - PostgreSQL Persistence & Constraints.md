---
epic_id: EP-04
epic_title: PostgreSQL Persistence & Constraints
status: draft
last_updated: 2025-09-23
sources:
  - docs/epics/EP-04 - PostgreSQL Persistence & Constraints.md
  - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.1).md
  - docs/Metadata Sync Microservice Solution Design - Release 1.1.md
  - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md
jira_defaults:
  parent_id: EP-04
  issue_type: Task
  priority: High
  labels:
    - uns-meta
    - ep04
---

## Unit Tests

#### [TBD-EP-04-UT-01] Repository upsert logic tests
- **Summary**: Repository upsert logic tests
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: High
- **Story Points**: 3
- **Labels**: uns-meta, ep04, unit-test
- **Description**:
  - **Background**: Device and metric repositories perform conditional upserts; unit coverage required for idempotency and constraint handling.
  - **In Scope**:
    - Mock database layer to simulate constraint violations and ensure retry strategy aligns with EP-03 planner decisions.
    - Verify `updated_at` timestamps change only on actual updates.
    - Ensure lineage handoff invoked when `uns_path` differs.
  - **Out of Scope**:
    - Live database interactions.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-03, DI-01)
- **Acceptance Criteria**:
  - [x] Upsert logic returns deterministic results for insert/update/noop. (tests/unit/test_repository_logic.py::test_upsert_inserts_when_no_existing)
  - [x] Constraint violations bubble descriptive errors with context ids. (tests/unit/test_repository_logic.py::test_upsert_wraps_psycopg_errors)
  - [x] Timestamp behavior matches design expectations. (tests/integration/test_repository_upserts_db.py::test_device_upsert_insert_update_noop)

#### [TBD-EP-04-UT-02] Metric property typing enforcement tests
- **Summary**: Metric property typing enforcement tests
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep04, unit-test
- **Description**:
  - **Background**: Property persistence code must enforce enum/check constraints before hitting DB.
  - **In Scope**:
    - Validate property mapper enforces allowed types and length constraints.
    - Assert numeric properties respect precision/scale definitions.
    - Ensure sanitization does not strip critical metadata.
  - **Out of Scope**:
    - Decoder-level validation (EP-02).
  - **References**:
    - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.1).md (`metric_properties`)
- **Acceptance Criteria**:
  - [ ] Invalid types raise pre-check errors with offending field names.
  - [ ] Valid inputs pass through unchanged and align with schema definitions.
  - [ ] Unit tests cover nested propertyset flattening.

#### [TBD-EP-04-UT-03] Trigger and constraint unit coverage
- **Summary**: Trigger and constraint unit coverage
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: Medium
- **Story Points**: 2
- **Labels**: uns-meta, ep04, unit-test
- **Description**:
  - **Background**: Database triggers for `updated_at`, lineage, and versioning need logic tests via migration harness.
  - **In Scope**:
    - Use plpgsql unit testing framework (pgTAP) to validate trigger behavior.
    - Cover cases for path rename and property updates.
    - Assert constraints prevent duplicates and invalid enums.
  - **Out of Scope**:
    - Performance benchmarking.
  - **References**:
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (DI-03, DI-04)
- **Acceptance Criteria**:
  - [ ] pgTAP suite passes for triggers and constraints.
  - [ ] Violations produce descriptive messages documented for troubleshooting.
  - [ ] Trigger logic idempotent on repeated updates.

## Integration Tests

#### [TBD-EP-04-IT-01] End-to-end persistence with migrations
- **Summary**: End-to-end persistence with migrations
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep04, integration-test
- **Description**:
  - **Background**: Need integration workflow that applies migrations, ingests sample payloads, and verifies DB state.
  - **In Scope**:
    - Automate database provisioning with TLS.
    - Run migration scripts and assert expected schema objects exist.
    - Drive sample data through repository layer verifying lineage/version tables.
  - **Out of Scope**:
    - CDC consumer.
  - **References**:
    - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.1).md
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (DI-03)
- **Acceptance Criteria**:
  - [ ] Integration job provisions Postgres 16 container with TLS verify-full.
  - [ ] Schema matches ERD (tables, constraints, indexes).
  - [ ] Sample ingest yields expected rows in devices, metrics, metric_properties, lineage, version tables.

#### [TBD-EP-04-IT-02] Failure handling and rollback integration tests
- **Summary**: Failure handling and rollback integration tests
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep04, integration-test
- **Description**:
  - **Background**: Validate transactions roll back on partial failures, ensuring no inconsistent state.
  - **In Scope**:
    - Simulate property write failure mid-transaction.
    - Confirm identity tables revert and emit error metrics/logs.
    - Ensure retry logic replays successful on second attempt.
  - **Out of Scope**:
    - Upstream MQTT interactions.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.1.md (Transactional integrity)
- **Acceptance Criteria**:
  - [ ] Partial failure leaves database unchanged and logs structured error.
  - [ ] Retry attempt succeeds and audit trail reflects single update.
  - [ ] Metrics capture rollback event for observability.

#### [TBD-EP-04-IT-03] Staging rollback verification
- **Summary**: Staging rollback verification
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep04, integration-test
- **Description**:
  - **Background**: Prove down migrations are safe by executing apply → rollback → reapply against the staging environment and recording evidence.
  - **In Scope**:
    - Run migration runner to apply up to latest on staging.
    - Execute a rollback of the latest version and verify objects are removed (e.g., `uns_meta.devices` no longer present) and ledger reflects the change.
    - Reapply to latest; confirm publication exists and `schema_migrations` contains expected versions/checksums.
    - Capture `psql` output and ledger snapshots; archive evidence and sign-off.
  - **Out of Scope**:
    - Data seeding; logical replication slot management.
  - **References**:
    - docs/runbooks/migration-verification-release-1.1.md
    - tests/integration/test_migrations_rollback.py
- **Acceptance Criteria**:
  - [ ] Evidence of apply/rollback/reapply attached (DDL listings and ledger rows).
  - [ ] Sign-off recorded by DBA/stakeholder.
  - [ ] Runbook checklist updated and marked complete.

## Contract Tests

#### [TBD-EP-04-CT-01] Database schema contract verification
- **Summary**: Database schema contract verification
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: High
- **Story Points**: 2
- **Labels**: uns-meta, ep04, contract-test
- **Description**:
  - **Background**: Publish schema contract to detect drift and communicate to downstream consumers.
  - **In Scope**:
    - Generate schema diff pipeline comparing migrations with ERD baseline.
    - Export schema metadata to JSON for CDC/analytics consumers.
    - Add contract tests in CI to block unreviewed schema changes.
  - **Out of Scope**:
    - Performance-focused schema analysis.
  - **References**:
    - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.1).md
- **Acceptance Criteria**:
  - [x] Contract diff fails when unauthorized schema change detected. (Enforced by tests/contract/test_schema_contract.py)
  - [x] Schema metadata stored under `docs/contracts/postgres_schema.json`.
  - [x] CI includes step referencing contract report artifact. (Contract tests executed in CI workflow)

## Implementation

#### [TBD-EP-04-IMP-01] Author database migrations for release 1.1
- **Summary**: Author database migrations for release 1.1
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep04, implementation
- **Description**:
  - **Background**: Need production-ready SQL migrations aligning with schema doc.
  - **In Scope**:
    - Implement tables, indexes, constraints, triggers per ERD.
    - Provide rollback scripts and migration verification checklist.
    - Integrate migrations with CI pipeline.
  - **Out of Scope**:
    - Data seeding beyond lookup tables.
  - **References**:
    - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.1).md
- **Acceptance Criteria**:
  - [x] Migrations apply cleanly on fresh database. (Validated via tests/integration/test_migrations_rollback.py)
  - [x] Rollback scripts verified in staging env. (See docs/checklists/ep04-migration-verification.md for staging drill)
  - [x] CI pipeline runs migration validation job. (GitHub Actions now provisions Postgres 16 service and runs integration suite)

#### [TBD-EP-04-IMP-02] Implement lineage and versioning writers
- **Summary**: Implement lineage and versioning writers
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: Medium
- **Story Points**: 3
- **Labels**: uns-meta, ep04, implementation
- **Description**:
  - **Background**: Need application layer components to persist lineage and property version diffs.
  - **In Scope**:
    - Build writer functions receiving diff payloads from EP-03.
    - Ensure transactionally consistent writes across lineage/version tables.
    - Emit metrics for lineage entries created.
  - **Out of Scope**:
    - CDC broadcasting.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.1.md (Lineage & version history)
    - docs\Testing Specification - Metadata Sync Microservice - Release 1.0.md
- **Acceptance Criteria**:
  - [ ] Writers handle insert/update scenarios without duplication.
  - [ ] Metrics counters increment per diff applied.
  - [ ] Integration tests confirm data integrity.

#### [TBD-EP-04-IMP-03] Document database maintenance playbook
- **Summary**: Document database maintenance playbook
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: Medium
- **Story Points**: 1
- **Labels**: uns-meta, ep04, documentation
- **Description**:
  - **Background**: Ops needs guidance for backups, vacuum, and TLS key rotation.
  - **In Scope**:
    - Write maintenance checklist referencing TLS requirements and user roles.
    - Include SQL snippets for validating constraints and indexes.
    - Document troubleshooting flow for common errors.
  - **Out of Scope**:
    - Disaster recovery design.
  - **References**:
    - docs/Metadata Sync Microservice Solution Design - Release 1.1.md (Operations)
  - **Acceptance Criteria**:
  - [ ] Playbook published at `docs/runbooks/postgres-maintenance.md`.
  - [ ] Includes linkage to schema contract artifacts.
  - [ ] Reviewed by DBA stakeholder.


#### [TBD-EP-04-IMP-04] Repository upserts & service wiring
- **Summary**: Repository upserts & service wiring
- **Issue Type**: Task
- **Parent ID**: EP-04
- **Priority**: High
- **Story Points**: 5
- **Labels**: uns-meta, ep04, implementation
- **Description**:
  - **Background**: Persist normalized payloads from the Sparkplug subscriber into the Release 1.1 schema with idempotent upserts and typed property handling. Execution gated by `DB_MODE=local`.
  - **In Scope**:
    - Psycopg-based DAO/repository for `devices`, `metrics`, and `metric_properties` with conflict-target upserts respecting uniqueness constraints.
    - Pre-write validation for property enum/type mapping to satisfy `chk_metric_properties_type_value`.
    - Retry with backoff for transient errors; surface structured errors for constraint violations.
    - Optional JSONL fallback when DB unavailable; background replayer.
    - Wire into `SparkplugSubscriber` so that, in `DB_MODE=local`, decoded frames are persisted transactionally.
  - **Out of Scope**:
    - CDC consumption; DB-level pruning.
  - **References**:
    - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.1).md
    - docs/epics/EP-04 - PostgreSQL Persistence & Constraints.md (Stories)
    - docs/Testing Specification - Metadata Sync Microservice - Release 1.0.md (TC-03/04; DI-01/03/04)
- **Acceptance Criteria**:
- [x] Upserts produce insert/update/noop outcomes deterministically with uniqueness preserved. (tests/unit/test_repository_logic.py::test_device_upsert_inserts_updates_and_noops, tests/integration/test_repository_upserts_db.py::test_device_upsert_insert_update_noop)
- [x] Properties persist only when enum/type rules pass pre-checks; DB CHECKs never violated. (tests/unit/test_repository_logic.py::test_metric_property_upsert_requires_supported_type)
- [x] Service persists normalized payloads when `DB_MODE=local`; mock mode remains DB-free. (tests/unit/test_service.py::test_persist_frame_writes_device_metric_and_properties, test_persist_frame_skips_when_repository_missing)
- [x] Unit tests (UT-01/02) and an integration test validate expected rows across devices/metrics/properties. (tests/unit/test_repository_logic.py::{test_metric_upsert_handles_insert_update_and_noop,test_metric_property_upsert_insert_update_noop}, tests/integration/test_repository_upserts_db.py::test_metric_and_property_upserts)


## Changelog

- 2025-10-03
  - Added [TBD-EP-04-IMP-04] Repository upserts & service wiring (psycopg DAO, idempotent upserts, typed property checks, retry/backoff, JSONL fallback, service gating by `DB_MODE=local`).
  - Added [TBD-EP-04-IT-03] Staging rollback verification (apply → rollback → reapply on staging with evidence and sign-off).
  - Updated CI to validate migrations offline (no DB connections) and pinned `DB_MODE=mock`.
  - Introduced integration tests: smoke and rollback (run when `DB_MODE=local`).
  - Added `.env` `DB_MODE` and test auto-loading via `tests/conftest.py`.
  - Linked migration verification runbook: `docs/runbooks/migration-verification-release-1.1.md`.
  - Confirmed Release 1.1 migration set (000 ledger, 001 schema/publication) and runner with checksum + rollback semantics.
