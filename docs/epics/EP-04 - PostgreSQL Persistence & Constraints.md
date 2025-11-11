---
id: EP-04
title: PostgreSQL Persistence & Constraints
status: done
owner: Product Trio (PM, Design, Tech Lead)
version: 1.0
sources:
  - ../Metadata Sync Microservice Solution Design - Release 1.0.md
  - ../Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.0).md
  - ../Testing Specification - Metadata Sync Microservice - Release 1.0.md
---

## Overview
Persist devices, metrics, and typed metric properties to PostgreSQL with strict constraints, triggers, lineage, and version history.

## Problem / Why
Durable, consistent storage is the foundation for CDC and downstream synchronization.

## Outcome
- DDL per schema doc; app upsert logic; `updated_at` triggers.
- Strict enum typing and CHECK constraints for metric properties.
- Lineage written on path rename; versions appended on property diffs.

## Scope
- In: DDL/migrations; idempotent upsert; lineage/version writes.
- Out: DB‑level pruning.

## Dependencies
- PostgreSQL 16.x; app and replication users; TLS.

## Acceptance Criteria (mapped tests)
- TC‑03, DI‑01, DI‑03: Idempotent upserts; uniqueness; timestamps.
- TC‑04, DI‑04: Typed property enforcement and round‑trip.
- TC‑06/07, DI‑05: Lineage and version history maintained.

## Stories
- Execute DDL; connect with TLS; manage credentials.
- Implement upsert for devices/metrics/properties.
- Detect path rename and write lineage; write version diffs for property changes.

## Risks / Mitigations
- Malformed data rejected by CHECK → Validate upstream; log DLQ entry if needed.

## Definition of Done
- All constraints satisfied during integration tests; verification SQL yields expected rows only.
