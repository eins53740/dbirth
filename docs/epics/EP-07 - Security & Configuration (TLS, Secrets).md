---
id: EP-07
title: Security & Configuration (TLS, Secrets)
status: planned
owner: Product Trio (PM, Design, Tech Lead)
version: 1.0
sources:
  - ../Metadata Sync Microservice Solution Design - Release 1.0.md
  - ../Testing Specification - Metadata Sync Microservice - Release 1.0.md
---

## Overview
Baseline security posture: TLS enforcement to EMQX and Postgres; secret handling via `.env` with least privilege.

## Problem / Why
Protect data in transit and avoid secret leakage.

## Outcome
- TLS 1.3 to EMQX; Postgres TLS verify‑full.
- No secrets in logs; config validation; principle of least privilege for users.

## Scope
- In: TLS config, trust stores, `.env` loading and validation, user permissions.
- Out: mTLS to EMQX (roadmap).

## Dependencies
- Ops‑provided certs/hosts; secret distribution.

## Acceptance Criteria (mapped tests)
- SEC‑01/02/03: TLS enforced; secrets respected; no sensitive logs.

## Stories
- TLS configuration and verification.
- Config loader with safe defaults and validation errors.
- Permissions for `uns_meta_app` and `uns_meta_cdc`.

## Risks / Mitigations
- Self‑signed in non‑prod → Explicit trust configuration + documentation.

## Definition of Done
- Security tests pass; start‑up fails fast on misconfiguration.
