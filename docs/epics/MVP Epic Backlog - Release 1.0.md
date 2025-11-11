---
title: Metadata Sync Microservice — MVP Epic Backlog (Release 1.0)
owner: Product Trio (PM, Design, Tech Lead)
status: draft
version: 1.0
sources:
  - ../Metadata Sync Microservice Solution Design - Release 1.0.md
  - ../Testing Specification - Metadata Sync Microservice - Release 1.0.md
---

# Overview

This backlog refines the MVP epics for Release 1.0 of the Metadata Sync Microservice, aligning scope and acceptance criteria with the solution design and the testing specification. The MVP focuses on ingesting DBIRTH metadata, persisting canonical metadata, generating diffs via CDC, and updating Canary reliably with minimal operational readiness.

Out of scope for MVP: mTLS to EMQX, additional CDC tables beyond `metrics` and `metric_properties`, advanced pruning/retention strategies, multi‑tenant partitioning, blue/green deploy automation.


# Epic List (MVP)

1. EP‑01 — Sparkplug DBIRTH Ingestion (EMQX)
2. EP‑02 — Payload Decode & Alias Resolution
3. EP‑03 — UNS Path Normalization & Identity Model
4. EP‑04 — PostgreSQL Persistence & Constraints
5. EP‑05 — CDC Diff Listener with Debounce
6. EP‑06 — Canary Write API Integration (Rate Limit, Retries)
7. EP‑07 — Security & Configuration (TLS, Secrets)
8. EP‑08 — Observability & Operational Readiness
9. EP‑09 — Test Infrastructure & Quality Gates


# EP‑01 — Sparkplug DBIRTH Ingestion (EMQX)

- Problem/Why: Service must reliably consume DBIRTH frames from EMQX over TLS to bootstrap metadata state.
- Outcome: Service subscribes to `spBv1.0/Secil/DBIRTH/#` (QoS 0), clean session true; handles reconnects and duplicates.
- Scope (In): MQTT client, subscription lifecycle, backpressure handling for bursts; basic watchdogs for connectivity.
- Scope (Out): NBIRTH/DCMD beyond alias/REBIRTH helper; mTLS.
- Dependencies: EMQX reachable; credentials in `.env`.
- Risks/Assumptions: QoS 0 frames may duplicate or drop; idempotent processing required.
- Acceptance Criteria:
  - Subscribes and remains connected with TLS 1.3; handles reconnects (TC‑10, SEC‑01).
  - Duplicate DBIRTH publishes do not create duplicates in DB (TC‑11, DI‑01).
  - Basic connectivity watchdog/logging present (OBS‑02/03).
- Stories:
  - MQTT client configuration (TLS 1.3, username/password).
  - Topic subscription management and reconnect policy.
  - Duplicate delivery tolerance and minimal buffering.


# EP‑02 — Payload Decode & Alias Resolution

- Problem/Why: Need to extract metric names/properties from Sparkplug payloads; support alias resolution continuity.
- Outcome: Decode binary payloads, map metrics, capture property sets; resolve names via cache; optional REBIRTH request with throttle.
- Scope (In): Binary decode; property set traversal; alias cache persistence; REBIRTH throttle.
- Scope (Out): Full dataset semantics beyond basic representation.
- Dependencies: `sparkplug_b_pb2.py`, `sparkplug_b_utils.py`.
- Risks/Assumptions: Incomplete alias maps; nested property structures.
- Acceptance Criteria:
  - Correct decode of binary fixtures (TC‑01).
  - Alias cache resolves names when absent; falls back to `alias:<id>` and may request REBIRTH (TC‑05).
  - Properties preserved and typed for persistence (TC‑04).
- Stories:
  - Implement decode and metrics extraction with properties.
  - Alias cache load/save and lookup precedence (device then node).
  - Optional REBIRTH publisher with per‑key throttle.


# EP‑03 — UNS Path Normalization & Identity Model

- Problem/Why: Canonical identity and pathing required for deduplication and downstream mapping.
- Outcome: Compute `devices.uns_path` and `metrics.uns_path` consistently; `metrics.canary_id` generated from path.
- Scope (In): Naming convention implementation; handling of country/business_unit/plant/edge/device/name.
- Scope (Out): Cross‑plant reconciliation and historical re‑pathing rules beyond lineage.
- Dependencies: Topic parsing; design’s path convention.
- Risks/Assumptions: Rename scenarios; stable convention.
- Acceptance Criteria:
  - Paths computed deterministically for fixtures (TC‑02).
  - `canary_id = replace(uns_path,'/','.')` holds (DI‑02).
- Stories:
  - Path normalizer module with tests.
  - Validation utilities to guard against illegal characters.


# EP‑04 — PostgreSQL Persistence & Constraints

- Problem/Why: Durable storage with strong constraints for devices, metrics, and typed properties.
- Outcome: Tables per schema doc; triggers for `updated_at`; strict enum typing in `metric_properties`.
- Scope (In): DDL as provided; upsert logic; lineage and versions tables available for MVP writes.
- Scope (Out): DB‑level pruning/retention.
- Dependencies: Postgres 16.x; application user.
- Risks/Assumptions: Strict checks may reject malformed data; intentional.
- Acceptance Criteria:
  - Inserts/upserts enforce uniqueness and triggers fire (TC‑03, DI‑01, DI‑03).
  - Typed property CHECK constraint enforced (TC‑04, DI‑04).
  - Lineage and versions tables writable by app (TC‑06/07, DI‑05).
- Stories:
  - Migrations/DDL execution and connection mgmt.
  - Idempotent upsert for devices/metrics/metric_properties.
  - Lineage write on `uns_path` change; version append on property diffs.


# EP‑05 — CDC Diff Listener with Debounce

- Problem/Why: Efficiently propagate metadata changes; reduce churn via debounce.
- Outcome: Logical replication consumer for `uns_meta_pub` (metrics, metric_properties); 3‑minute debounce per metric before emitting.
- Scope (In): Connect via `pgoutput`; compute diffs; maintain small in‑memory buffers.
- Scope (Out): Cross‑service event bus or DLQ (unless required for retries in EP‑06).
- Dependencies: Publication exists; replication user.
- Risks/Assumptions: Debounce window trade‑off; memory for buffers.
- Acceptance Criteria:
  - Publication scope verified (TC‑15).
  - Burst updates yield single aggregated diff post‑debounce (TC‑16).
  - Order preserved and diffs correct (TC‑17).
- Stories:
  - CDC client wiring; reconnect and lag metrics.
  - Per‑metric debounce buffer; diff computation.
  - Emission to Canary client queue with idempotency key.


# EP‑06 — Canary Write API Integration (Rate Limit, Retries)

- Problem/Why: Push updates to Canary reliably without violating SLOs.
- Outcome: Transform diffs to Canary `storeTagData` payload; enforce 500 rps; implement retries with exp backoff + jitter; circuit breaker.
- Scope (In): HTTP client; auth token; rate limiter; retry/circuit policy; de‑duplication.
- Scope (Out): Canary read APIs or bulk sync beyond diffs.
- Dependencies: Canary endpoint, token in `.env`.
- Risks/Assumptions: Transient 5xx; network instability.
- Acceptance Criteria:
  - Payload conforms to contract (TC‑20).
  - Sustained load respects 500 rps (TC‑21).
  - 5xx triggers retry policy and circuit breaker, with recovery (TC‑22).
- Stories:
  - Mapper from internal model to Canary request.
  - Token auth, HTTP client with timeouts.
  - Token‑bucket/queue‑based rate limiter; retry + circuit breaker.


# EP‑07 — Security & Configuration (TLS, Secrets)

- Problem/Why: Secure connectivity and secret management baseline.
- Outcome: TLS 1.3 to EMQX; Postgres TLS verify‑full; secrets from `.env` with least privilege.
- Scope (In): Certificate validation; config validation; principle of least privilege for DB users.
- Scope (Out): mTLS to EMQX (post‑MVP roadmap).
- Dependencies: Ops‑provided certs/hosts.
- Risks/Assumptions: Self‑signed certs in non‑prod; documented trust store.
- Acceptance Criteria:
  - MQTT and Postgres TLS enforced, credentials not logged (SEC‑01/02/03).
  - `.env` secrets respected; config errors fail fast with clear logs.
- Stories:
  - TLS configuration, trust store handling.
  - Config loader with validation and safe defaults.


# EP‑08 — Observability & Operational Readiness

- Problem/Why: Operate service safely and diagnose issues quickly.
- Outcome: Prometheus metrics; structured JSON logs; minimal watchdog alerts.
- Scope (In): Metrics for ingest, decode errors, DB writes, CDC events, Canary requests, retries, circuit state, rate limiting; JSON logs.
- Scope (Out): Full alert catalog and dashboards (initial minimal set only).
- Dependencies: Metrics endpoint scraped by Prometheus; log aggregation available.
- Risks/Assumptions: Low overhead for metrics.
- Acceptance Criteria:
  - Metrics and logs expose golden signals (OBS‑01/02).
  - Watchdog alerts for sustained failures, circuit open, CDC lag (OBS‑03).
- Stories:
  - Metrics registry and counters/gauges/histograms.
  - Structured logging with correlation IDs.
  - Basic alerting rules documented.


# EP‑09 — Test Infrastructure & Quality Gates

- Problem/Why: Ensure correctness and prevent regressions.
- Outcome: Fixture‑driven tests for Sparkplug parsing; integration tests for MQTT→DB and CDC→Canary; Canary mock; SQL verification scripts; CI pipeline gates.
- Scope (In): Unit, integration, E2E smoke (with mocks); verification SQL; coverage thresholds.
- Scope (Out): Performance load tests beyond smoke rate‑limit checks.
- Dependencies: Test fixtures; CI runners; containerized services.
- Risks/Assumptions: Network‑less CI using mocks.
- Acceptance Criteria:
  - Tests mapped to TC/DI/SEC/OBS pass (Section 6/7 of Testing Spec).
  - CI gates block on failures; artifacts include logs/metrics snapshots.
- Stories:
  - Curate fixtures; add Canary mock with failure modes.
  - Write verification SQL scripts and helpers.
  - CI workflow with parallel test stages and summaries.


# MVP Milestones & Cutlines

- M1: Ingest + Decode + Normalize (EP‑01..03)
- M2: Persistence + Constraints (EP‑04)
- M3: CDC Diff + Debounce (EP‑05)
- M4: Canary Integration with Reliability (EP‑06)
- M5: Security + Observability Baseline (EP‑07..08)
- M6: Test & CI Readiness (EP‑09)


# Metrics of Success (MVP)

- Functional: 100% pass on TC‑01..07, TC‑10..22, TC‑30..31; DI‑01..05; SEC‑01..03; OBS‑01..03 in the Testing Specification.
- Reliability: 0 duplicate rows in DB under duplicate DBIRTH; 0 missed Canary updates under transient 5xx (post‑retry).
- Performance: Sustained 500 rps compliance with zero 429s; average Canary request latency within configured timeout.
- Operability: Alerts fire for sustained failures; logs/metrics adequate for incident triage within 15 minutes.


# Dependencies & Externalities

- EMQX access and credentials provisioned.
- Postgres instance with TLS and publication created.
- Canary endpoint and token; rate limit expectations confirmed.
- Prometheus scrape target and log aggregation available.


# Risks & Mitigations

- Duplicate/late DBIRTH frames → Idempotent upserts; unique constraints; retries safe.
- Schema mismatch or malformed properties → Strict typing with clear validation and dead‑letter logging if needed (non‑blocking).
- Canary outages → Circuit breaker and retry with jitter; backlog queuing.
- CDC lag or slot issues → Lag metrics, alerting, and safe reconnect logic.


# Definition of Done (MVP)

- All epic acceptance criteria met and mapped tests pass per Testing Specification.
- Runbook drafted: connectivity, config, troubleshooting, and rollback steps.
- Minimal dashboards or metric descriptions shared with Ops.
