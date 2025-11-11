---
id: EP-02
title: Payload Decode & Alias Resolution
status: done
owner: Product Trio (PM, Design, Tech Lead)
version: 1.0
sources:
  - ../Metadata Sync Microservice Solution Design - Release 1.0.md
  - ../Testing Specification - Metadata Sync Microservice - Release 1.0.md
---

## Overview
Decode Sparkplug B DBIRTH payloads, capture metric properties, and resolve metric names using alias cache with optional REBIRTH requests.

## Problem / Why
DBIRTH often carries aliases; name and property extraction is essential for consistent metadata.

## Outcome
- Correctly decode binary payloads; traverse property sets (including nested/propertyset(s)).
- Resolve names via alias cache (device → node fallback), else `alias:<id>`; optional REBIRTH with throttle.

## Scope
- In: Binary decode, properties traversal, alias cache persistence, REBIRTH throttle.
- Out: Advanced DataSet semantics beyond basic representation.

## Dependencies
- `sparkplug_b_pb2.py`, `sparkplug_b_utils.py`.

## Acceptance Criteria (mapped tests)
- TC‑01: Correct decode of binary fixtures.
- TC‑05: Alias cache resolves names; REBIRTH optional and throttled.
- TC‑04: Properties preserved and typed for persistence.

## Stories (implemented)
- Decode and extract metrics + properties.
- Alias cache load/save and lookup precedence.
- Optional REBIRTH publisher with per‑key throttle.

## Risks / Mitigations
- Incomplete alias maps → Cache persisted on BIRTH; REBIRTH throttle prevents storms.

## Definition of Done
- Acceptance criteria pass using provided fixtures; logs show stable alias behavior.
