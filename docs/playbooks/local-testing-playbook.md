---
title: Local Testing Playbook — Metadata Sync Microservice
status: draft
owner: UNS Team
version: 1.0
---

# Overview

This playbook explains how to run the project’s Unit, Integration, and Contract tests on a developer workstation using Python 3.13 and uv for dependency management. It aligns with the Testing Specification (Release 1.0) and the epics/tasks under `docs/epics` and `docs/tasks`.

Key goals:
- Favor offline tests by default: use fixtures and mocks; gate network tests with an env flag.
- Keep Postgres tests local-first (localhost), with Testcontainers as a future option.
- Enforce practical coverage thresholds per suite: 70% (unit), 30–50% (integration).


# Prerequisites

- Python 3.13 installed and available on PATH.
- uv (dependency and tool runner) installed.
- Git (optional for pre-commit hooks).

Install uv:
- Windows PowerShell: `pipx install uv` or `py -m pip install --user uv`
- macOS/Linux: `pipx install uv` or `python3 -m pip install --user uv`

Create a virtual environment and activate it:
- Windows PowerShell
  - `uv venv --python 3.13`
  - `./.venv/Scripts/Activate.ps1`
- macOS/Linux
  - `uv venv --python 3.13`
  - `source .venv/bin/activate`


# Project Dependencies

Runtime (current codebase):
- `paho-mqtt`, `python-dotenv`, `protobuf`

Testing and tooling:
- `pytest`, `pytest-cov`, `pytest-xdist`
- `ruff` (lint) and `black` (format)
- `mypy` (optional static typing)
- Integration DB: `psycopg[binary]` (psycopg 3) or `psycopg2-binary` (fallback)
- Contract tests: `jsonschema`
- Optional Canary mock (local): `fastapi`, `uvicorn`
- Future (optional): `testcontainers[postgres]`

Install with uv (example):
- Windows PowerShell
  - `uv pip install paho-mqtt python-dotenv protobuf pytest pytest-cov pytest-xdist ruff black mypy jsonschema fastapi uvicorn psycopg[binary]`
- macOS/Linux
  - `uv pip install paho-mqtt python-dotenv protobuf pytest pytest-cov pytest-xdist ruff black mypy jsonschema fastapi uvicorn psycopg[binary]`

Notes:
- If `psycopg[binary]` fails on your OS/Python, try `psycopg2-binary`.
- You can also run tools without installing them into the venv via `uvx`, e.g., `uvx ruff check .`.


# Environment Variables

Create a `.env` at the repo root with the following keys (keep secrets out of Git):

```
MQTT_HOST=scunsemqx.secil.pt
MQTT_PORT=8883
MQTT_USER=...
MQTT_PASSWORD=...
PGHOST=localhost
PGPORT=5432
PGDATABASE=uns_metadata
PGUSER=postgres
PGPASSWORD=        # intentionally blank for local default
CANARY_TOKEN=...   # only used if network tests are enabled
ENABLE_NETWORK_TESTS=0
```

Windows PowerShell quick set (session only):
- `$env:ENABLE_NETWORK_TESTS="0"`

macOS/Linux (bash):
- `export ENABLE_NETWORK_TESTS=0`


# Test Layout and Markers

Recommended structure:
- `tests/unit/...` (pytest `-m unit`)
- `tests/integration/...` (pytest `-m integration`)
- `tests/contract/...` (pytest `-m contract`)
- `tests/fixtures/...` (golden inputs: Sparkplug DBIRTH `.bin` and decoded `.json`)

Configure markers and defaults (add to `pyproject.toml` or `pytest.ini`):

```toml
[tool.pytest.ini_options]
markers = [
  "unit: fast, isolated",
  "integration: db/mocks/slow",
  "contract: schema/fixture contracts"
]
addopts = "-ra"
```

Coverage strategy:
- Unit suite: `--cov` with `--cov-fail-under=70`
- Integration suite: `--cov` with `--cov-fail-under=30` (raise to 50% when feasible)
- Contract suite: no fail-under required initially (optional 50%)


# Local Postgres (Integration & Data Integrity)

Primary path: Local Postgres at `localhost:5432`, database `uns_metadata`, schema `uns_meta`, user `postgres` with no password.

1) Create database and schema (Windows example with `psql` on PATH):
- PowerShell: `psql -h localhost -U postgres -c "CREATE DATABASE uns_metadata;"`
- Apply DDL from the schema doc:
  - `psql -h localhost -U postgres -d uns_metadata -f "docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.1).md"` (copy SQL into a `.sql` file if needed)

2) Reset between test runs:
- Option A: Drop and recreate schema
  - `psql -h localhost -U postgres -d uns_metadata -c "DROP SCHEMA IF EXISTS uns_meta CASCADE; CREATE SCHEMA uns_meta;"`
- Option B: Run an idempotent DDL script that recreates tables, types, and triggers.

3) Running integration tests (examples):
- Unit + coverage: `uv run pytest -m unit --cov=. --cov-report=term-missing --cov-fail-under=70 -q`
- Integration (DB): `uv run pytest -m integration --cov=. --cov-report=term-missing --cov-fail-under=30 -q`

Future option — Testcontainers (isolated DB):
- Install `testcontainers[postgres]` and run integration tests with a PostgreSQL container managed in test fixtures. This removes the need for a local DB and ensures clean state per run.


# Contract Tests

Sparkplug DBIRTH decode contract (CT-01):
- Place golden fixtures under `tests/fixtures/spb/`
  - Example filenames:
    - `messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.bin`
    - `messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json`
- If you don’t have these in the repo yet, add your local golden fixture now or share it to include in version control.
- Tests should decode `.bin` and assert exact field parity with `.json` (names/aliases, datatypes, timestamps, property sets).

Canary API contract (CT-02):
- Prefer a JSON Schema for `POST /api/v2/storeTagData` requests and responses under `docs/contracts/` (e.g., `canary_storeTagData.schema.json`).
- Validate with `jsonschema` in tests.
- Optional local mock server using FastAPI to exercise the client end-to-end without the external network.

Minimal FastAPI mock snippet (optional):

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

class Tag(BaseModel):
    id: str
    properties: dict

app = FastAPI()

@app.post("/api/v2/storeTagData")
def store_tag_data(tags: list[Tag]):
    # Insert schema validations here (jsonschema or pydantic)
    return {"accepted": len(tags)}

# Run: uv run uvicorn canary_mock:app --reload --port 55293
```

Run contract tests:
- `uv run pytest -m contract -q`


# MQTT and Network Tests (Optional)

Default behavior: tests stay offline using fixtures/mocks (`ENABLE_NETWORK_TESTS=0`).

Enable with caution:
- PowerShell: `$env:ENABLE_NETWORK_TESTS="1"`
- Bash: `export ENABLE_NETWORK_TESTS=1`

When enabled, you can point tests at EMQX/Canary over the network using `.env` values. Keep these out of CI unless explicitly permitted.


# Linting, Formatting, and Types

Ruff (lint):
- Check: `uvx ruff check .`
- Fix: `uvx ruff check . --fix`

Black (format):
- Check: `uvx black --check .`
- Format: `uvx black .`

Mypy (optional type check):
- `uv run mypy .`

Suggested `pyproject.toml` snippets:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.black]
line-length = 100
target-version = ["py313"]

[tool.mypy]
python_version = "3.13"
ignore_missing_imports = true
```


# Pytest Commands Quick Reference

- Unit only: `uv run pytest -m unit -q`
- Integration only: `uv run pytest -m integration -q`
- Contract only: `uv run pytest -m contract -q`
- All with coverage: `uv run pytest --cov=. --cov-report=term-missing -q`
- Parallel (if needed): `uv run pytest -n auto -q`


# Pre-commit Hooks (Recommended)

Set up a basic pre-commit to keep the repo clean:

1) Install: `uv pip install pre-commit`
2) Create `.pre-commit-config.yaml` with hooks for Ruff, Black, and end-of-file fixes.
3) Enable: `uv run pre-commit install`

Sample config:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: ["--fix"]
  - repo: https://github.com/psf/black
    rev: 24.8.0
    hooks:
      - id: black
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
```


# CDC Tests (Placeholder)

Until the CDC client (logical replication, debounce, diff) is implemented:
- Keep a placeholder `tests/integration/test_cdc_placeholder.py` that asserts a skipped status with a rationale.
- Once available, add fixtures to spin up a Postgres publication `uns_meta_pub` and connect a `pgoutput` client.
- Consider contract-testing internal diff objects with a JSON Schema (`docs/contracts/cdc_diff.schema.json`).


# Troubleshooting

- Python 3.13 wheels: If a library lacks 3.13 wheels, pin a compatible version or switch to `psycopg2-binary` for tests.
- TLS verification: Avoid disabling TLS verification in tests. Provide CA where necessary.
- Local Postgres auth: Ensure `pg_hba.conf` allows local connections without a password for user `postgres`, or set `PGPASSWORD` and reload.
- Windows paths: Use PowerShell-friendly paths and quote file paths with spaces.


# Next Steps

- Place your golden DBIRTH fixtures under `tests/fixtures/spb/` (bin + json) and commit.
- Add JSON Schema for Canary under `docs/contracts/` to enable contract tests.
- If you prefer, I can scaffold a minimal tests folder with markers and placeholder tests to get you started.
