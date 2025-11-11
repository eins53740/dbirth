---
id: EP-03
title: UNS Path Normalization & Identity Model
status: done
owner: Product Trio (PM, Design, Tech Lead)
version: 1.0
sources:
  - ../Metadata Sync Microservice Solution Design - Release 1.0.md
  - ../Testing Specification - Metadata Sync Microservice - Release 1.0.md
---

## Overview
Compute canonical UNS paths for devices and metrics and generate `canary_id` from metric path.

## Problem / Why
Deterministic identity prevents duplicates, enables idempotent updates, and maps cleanly to Canary.

## Outcome
- `devices.uns_path` and `metrics.uns_path` computed from topic/payload conventions.
- `metrics.canary_id = replace(uns_path,'/','.')` maintained automatically.

## Scope
- In: Path normalization module; validation of inputs; unit tests.
- Out: Cross‑plant reconciliation beyond lineage.

## Dependencies
- Topic parsing; naming convention from design.

## Acceptance Criteria (mapped tests)
- TC‑02: Deterministic path computation for fixtures.
- DI‑02: `canary_id` matches path transformation.

## Stories
- Implement normalizer for device and metric paths.
- Validate/escape illegal characters per convention.
- Add unit tests using fixtures.

## Risks / Mitigations
- Renames across hierarchy → Covered by lineage in EP‑04.

## Definition of Done
- Paths consistent across runs; all tests pass.
