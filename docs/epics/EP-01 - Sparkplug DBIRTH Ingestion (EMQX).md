---
id: EP-01
title: Sparkplug DBIRTH Ingestion (EMQX)
status: done
owner: Product Trio (PM, Design, Tech Lead)
version: 1.0
sources:
  - ../Metadata Sync Microservice Solution Design - Release 1.0.md
  - ../Testing Specification - Metadata Sync Microservice - Release 1.0.md
---

## Overview
Reliable ingestion of Sparkplug B DBIRTH frames from EMQX over TLS to bootstrap and refresh metadata state. Current codebase provides initial implementation.

## Problem / Why
Without stable ingestion, no downstream metadata persistence or synchronization is possible.

## Outcome
- Subscribe to `spBv1.0/Secil/DBIRTH/#` (QoS 0), clean session true.
- Handle reconnects and duplicate delivery; basic connectivity watchdogs/logs.

## Scope
- In: MQTT client lifecycle, TLS 1.3, subscription/reconnect policies, duplicate tolerance.
- Out: mTLS (post‑MVP), non‑DBIRTH topics beyond alias/REBIRTH helper.

## Dependencies
- EMQX reachable; credentials in `.env`.

## Acceptance Criteria (mapped tests)
- TC‑10, SEC‑01: TLS 1.3 connect and subscribe; reconnects handled.
- TC‑11, DI‑01: Duplicates do not create DB duplicates (via idempotent processing + constraints).
- OBS‑02/03: Connectivity logs and basic watchdogs present.

## Stories (implemented)
- MQTT client with TLS and credentials.
- Topic subscription and reconnect policy.
- Duplicate tolerance and minimal buffering.

## Risks / Mitigations
- QoS 0 duplicates/drops → Idempotent processing; unique constraints downstream.

## Definition of Done
- Acceptance criteria pass; connected reliably in dev/staging; logs show stable subscription.
