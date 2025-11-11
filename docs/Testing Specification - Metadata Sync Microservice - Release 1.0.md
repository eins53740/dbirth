---
title: Metadata Sync Microservice - Testing Specification (Release 1.1)
status: draft
owner: UNS Team
version: 1.1
sources:
  - docs/Metadata Sync Microservice Solution Design - Release 1.1.md
  - docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.1).md
---

# 1. Purpose & Scope

This document defines the testing strategy, scenarios, and acceptance criteria for the Metadata Sync Microservice as specified in the solution design and schema/ERD (Release 1.1). It focuses on unit, integration, and contract tests (with data integrity validated as part of integration) needed to validate ingestion of Sparkplug B DBIRTH metadata, persistence to PostgreSQL, CDC-based diffing, and propagation to the Canary Write API.

Out of scope: provisioning of EMQX/PostgreSQL/Canary infrastructure, deep penetration testing, UI/UX, and non-functional/performance testing.


# 2. System Overview (Test-Relevant)

- Input: MQTT Sparkplug B DBIRTH frames from EMQX (`spBv1.0/Secil/DBIRTH/#`, TLS 1.3, username/password).
- Processing: decode payload, normalize to UNS paths, upsert devices/metrics/typed metric_properties; write audit trail (metric_versions) and lineage on renames.
- CDC: logical replication publication `uns_meta_pub` (metrics, metric_properties) + diff listener with debounce.
- Output: Canary Write API `POST /api/v2/storeTagData` with rate-limit, retries, and circuit breaker.
- Observability (context): Prometheus metrics and JSON logs (not directly tested as a separate suite in this spec).

References:
- Design: docs/Metadata Sync Microservice Solution Design - Release 1.0.md
- Schema/ERD: docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.0).md


# 3. Test Strategy

- Unit tests: parsing/normalization, property typing, idempotent upsert logic, diff computation, retry/backoff utilities.
- Integration tests: MQTT ingest -> DB writes; DB writes -> CDC consumer; CDC consumer -> Canary client. Include rate limiting, retries, and circuit breaker behavior using a mock Canary.
- Contract tests: Sparkplug payload decode (golden binary and JSON fixtures); Canary request/response schema validation via a mock server.
- Integration (data integrity and constraints): constraints, triggers, generated columns, lineage, and versioning validated against a real local PostgreSQL instance.

Integration boundaries:
- MQTT ingest -> DB writes
- DB writes -> CDC diff/debounce
- CDC consumer -> Canary client

Guiding principles:
- Deterministic fixtures and environment-seeded secrets.
- No network to external systems unless mocked or explicitly allowed.
- Use realistic DBIRTH frames from fixtures.


# 4. Test Environments

Environment profiles:
- Local: Python runtime with localhost PostgreSQL 16.x (db `uns_metadata`, schema `uns_meta`). EMQX and Canary are reachable on the network but tests default to mocks/fixtures (no external calls) unless explicitly enabled for manual checks.
- Staging: real EMQX/Canary with safe namespaces and credentials (smoke tests only).
- CI (future): GitHub runners planned; ephemeral Postgres and mocks/fixtures; no dependence on external EMQX/Canary.

Config inputs:
- `.env` with `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD`, `PG_*`, `CANARY_TOKEN`, rate-limit and retry parameters.


# 5. Test Data & Fixtures

Sparkplug DBIRTH examples in repo:
- `messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.bin` (binary)
- `messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json` (decoded JSON)

Fixtures to curate:
- Minimal DBIRTH with 1 device, 2 metrics, simple properties.
- Complex DBIRTH with nested property sets and dataset values.
- DBIRTH with aliases only (no names), followed by NBIRTH/DBIRTH resolving aliases.
- Rename scenario: metric `uns_path` changes, requiring lineage.
- Property change scenario: only property key/value changes (no path change).

DB seeds:
- Run DDL from: docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.0).md
- Ensure publication `uns_meta_pub` created; replication slot created by app.


# 6. Test Cases

Notation: TC-XX (Unit/Integration), DI-XX (Integration - Data Integrity), CT-XX (Contract).

## 6.1 Unit - Parsing and Utilities

- TC-01 Parse Sparkplug DBIRTH (binary)
  - Input: `.bin` fixture
  - Expected: decoded metrics with correct names/aliases, datatypes, timestamps, and property sets preserved.

- TC-02 Normalize to UNS paths
  - Input: decoded metrics with group/country/business_unit/plant/edge/device/name from topic/payload
  - Expected: `devices.uns_path` and `metrics.uns_path` computed per naming convention; `metrics.canary_id` equals `uns_path` with `/` replaced by `.`.

- TC-03 Upsert logic (idempotent)
  - Input: first vs repeated DBIRTH for a device
  - Expected: change detection yields no-op on identical input; only differences produce updates.

- TC-04 Typed metric properties mapping
  - Input: properties across enum types (`int|long|float|double|string|boolean`)
  - Expected: exactly one typed value is set per property based on type.

- TC-05 Diff computation utilities
  - Input: prior and new metric/property states
  - Expected: stable, deterministic diffs capturing path, name, and property changes.

- TC-06 Retry/backoff utilities
  - Input: transient error sequences
  - Expected: exponential backoff with jitter schedule produced as configured; max attempts enforced.

## 6.2 Integration - MQTT Ingest -> DB

- TC-10 Ingest device and metrics
  - Action: feed DBIRTH via ingestion driver or mock MQTT publisher using fixtures
  - Expected: rows in `uns_meta.devices` and `uns_meta.metrics` inserted/updated; repeated DBIRTH is idempotent.

- TC-11 Typed metric properties persisted
  - Action: ingest metrics with all property types
  - Expected: one typed column set per row; values round-trip from payload to DB.

- TC-12 Alias resolution fallback
  - Action: metrics with alias but missing name; cache has prior alias mapping
  - Expected: names resolved from cache; fallback behavior defined if missing.

- TC-13 Lineage on UNS path rename
  - Action: publish DBIRTH with renamed metric path
  - Expected: lineage recorded; versions updated.

## 6.3 Integration - DB -> CDC

- TC-15 Debounced CDC emission
  - Action: multiple updates within debounce window
  - Expected: aggregated diff emitted once per key.

- TC-16 Diff content correctness
  - Action: update only properties, then rename path, then both
  - Expected: emitted diffs reflect exact changes in order.

- TC-17 Ordering and timestamps
  - Action: sequence two changes with slight delay
  - Expected: chronological `changed_at` and correct diffs.

## 6.4 Integration - CDC -> Canary

- TC-20 Canary payload correctness
  - Expected: payload maps `metrics.canary_id` and selected properties to Canary `storeTagData` format; conforms to API contract (fields, types).

- TC-21 Rate limiting
  - Setup: 500 req/s cap (mock enforces)
  - Action: enqueue >500 updates per second via CDC
  - Expected: client throttles requests, no 429 bursts; backlog drains steadily.

- TC-22 Retries and circuit breaker
  - Action: make Canary mock return 5xx; verify exponential backoff with jitter (6 attempts), then open circuit; after cool-down, half-open and recover.
  - Expected: retry schedule observed; no data loss (retries or DLQ if implemented); metrics reflect states.

## 6.5 Contract Tests

- CT-01 Sparkplug payload decode contract
  - Basis: golden `.bin` and `.json` fixtures
  - Expected: decoder output matches canonical fields (names/aliases, datatypes, timestamps, property sets) for all fixtures; no broker required.

- CT-02 Canary API request/response contract
  - Basis: JSON Schema for `POST /api/v2/storeTagData` requests and expected responses
  - Setup: lightweight mock server validates requests against schema and returns schema-conformant responses; supports configurable failures for negative paths
  - Expected: client generates schema-valid payloads and correctly handles response variants (2xx, 4xx validation errors surfaced, 5xx retriable)

## 6.6 Integration - Data Integrity & Constraints

- DI-01 Unique identities
  - Expected: `devices` unique `(group_id,edge,device)`; `metrics` unique `(device_id,name)`; both `uns_path` unique.

- DI-02 Generated columns
  - Expected: `metrics.canary_id = replace(uns_path,'/','.')` matches expectation on insert/update.

- DI-03 Timestamps
  - Expected: `updated_at` triggers fire on update; `created_at` immutable.

- DI-04 Property type check
  - Expected: CHECK constraint enforces exactly one column set per row for given `type`.

- DI-05 Lineage and versions
  - Expected: lineage uniqueness holds; version history append-only.


# 7. Verification Queries (PostgreSQL)

Use these queries to validate outcomes of test cases:

```sql
-- Devices/metrics persisted
SELECT d.device_id, d.uns_path AS device_path, m.metric_id, m.name, m.uns_path AS metric_path, m.canary_id
FROM uns_meta.devices d
JOIN uns_meta.metrics m ON m.device_id = d.device_id
ORDER BY d.device_id, m.metric_id;

-- Typed properties for a metric
SELECT key, type, value_int, value_long, value_float, value_double, value_string, value_bool
FROM uns_meta.metric_properties
WHERE metric_id = $1
ORDER BY key;

-- Versions (diff trail)
SELECT metric_id, changed_at, changed_by, diff
FROM uns_meta.metric_versions
WHERE metric_id = $1
ORDER BY changed_at DESC;

-- Lineage
SELECT metric_id, old_uns_path, new_uns_path, changed_at
FROM uns_meta.metric_path_lineage
WHERE metric_id = $1
ORDER BY changed_at DESC;

-- Constraint checks (expect no rows)
-- Duplicate metric by (device_id, name)
WITH dup AS (
  SELECT device_id, name, COUNT(*) c FROM uns_meta.metrics GROUP BY 1,2 HAVING COUNT(*) > 1
) SELECT * FROM dup;

-- Uns_path uniqueness violations (should be empty)
WITH dup AS (
  SELECT uns_path, COUNT(*) c FROM uns_meta.metrics GROUP BY 1 HAVING COUNT(*) > 1
) SELECT * FROM dup;
```


# 8. Tooling & Mocks

- Sparkplug decode: use repo `sparkplug_b_pb2.py` and `sparkplug_b_utils.py` to decode fixtures and validate parse logic.
- MQTT publisher: fixture ingestion driver or `paho-mqtt` publisher; prefer fixtures/mocks for tests; optionally use EMQX locally for manual checks.
- Canary mock: lightweight HTTP server capturing requests and enforcing rate limits; configurable failure modes for retry/circuit tests; validates requests against JSON Schema for contract tests.
- CDC driver: prefer a `pgoutput` logical replication client for integration tests; triggers can simulate CDC events where a replication client is impractical.


# 9. Acceptance Criteria

- Unit (TC), Integration (TC + DI), and Contract (CT) test suites pass in the local environment; staging smoke tests pass where applicable.
- No uniqueness or type constraint violations in DB during test runs.


# 10. Traceability

- MQTT subscription, QoS/Session, credentials: Design - System Connections (EMQX)
- DB schema, constraints, publications: Schema/ERD DDL and ERD
- CDC + debounce + diffing: Design - Data Flow and CDC notes
- Canary write endpoint, rate limit, retry/circuit: Design - Canary Write API


# 11. Execution Notes

- Prefer mocked EMQX/Canary in automated runs to avoid external network dependencies.
- Fix seeds between tests; reset DB schema between suites.
- Use fixture-driven tests for Sparkplug parsing to guarantee determinism.
- Capture request/response transcripts for the Canary mock and assert on them.


# 12. Appendix - Setup Snippets

Run schema DDL (excerpt), see full DDL in the schema doc:

```sql
CREATE SCHEMA IF NOT EXISTS uns_meta;
-- tables: devices, metrics, metric_properties, metric_versions, metric_path_lineage
-- publication: uns_meta_pub (metrics, metric_properties)
```

Sample env (do not commit secrets):

```bash
MQTT_HOST=scunsemqx.secil.pt
MQTT_PORT=8883
MQTT_USER=...
MQTT_PASSWORD=...
PGHOST=localhost
PGPORT=5432
PGDATABASE=uns_metadata
PGUSER=uns_meta_app
PGPASSWORD=...
CANARY_TOKEN=...
```

---

Changelog:
- 1.1: Refocused spec on unit, integration, and contract tests; removed E2E, security, and observability sections; reclassified data integrity under integration; updated environments and acceptance criteria.
