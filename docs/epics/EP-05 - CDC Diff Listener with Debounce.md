---
id: EP-05
title: CDC Diff Listener with Debounce
status: done
owner: Product Trio (PM, Design, Tech Lead)
version: 1.0
sources:
  - ../Metadata Sync Microservice Solution Design - Release 1.0.md
  - ../Testing Specification - Metadata Sync Microservice - Release 1.0.md
---

## Overview
Consume logical replication (`pgoutput`) from publication `uns_meta_pub` and emit aggregated diffs after a debounce window per metric.

## Problem / Why
Avoid noisy downstream updates while ensuring timely propagation of changes.

## Outcome
- Connect to publication; compute per‑metric diffs; apply 3‑minute debounce; emit minimal updates.

## Scope
- In: CDC client; per‑metric buffering; diff computation; reconnect handling.
- Out: External event bus or DLQ (unless required by EP‑06 retries).

## Dependencies
- Publication exists on `metrics` and `metric_properties`; replication user.

## Acceptance Criteria (mapped tests)
- TC‑15: Publication scope verified.
- TC‑16: Debounce aggregates bursts into minimal emissions.
- TC‑17: Order is preserved in versions and diffs.

## Stories
- Implement CDC client and reconnection.
- Debounce buffer keyed by metric; timer management.
- Diff generator; emit to Canary queue with idempotency.

## Risks / Mitigations
- Memory growth for buffers → Cap and spill or shorten window if needed.

## Definition of Done
- CDC lag/throughput observable; tests pass for debounce and order guarantees.
