# Migration Verification – Release 1.1

This checklist validates the Release 1.1 PostgreSQL schema before promoting migrations.

## Prerequisites
- Python 3.13 with `uv sync --locked --all-extras --dev` executed.
- `DB_MODE` exported to `local` when validating against a live Postgres 16 instance.
- Service `.env` updated with correct `PG*` connection variables.

## Verification Steps
1. **Static validation**
   - `uv run python -m uns_metadata_sync.migrations apply --dry-run`
   - `uv run python -m uns_metadata_sync.migrations rollback --dry-run`
2. **Fresh database apply** (local Postgres only)
   - `uv run python -m uns_metadata_sync.migrations apply`
   - Confirm rows in `public.schema_migrations` for versions `000` and `001`.
3. **Rollback smoke test**
   - `uv run python -m uns_metadata_sync.migrations rollback`
   - `uv run python -m uns_metadata_sync.migrations apply --target-version 001`
4. **Test suite**
   - `uv run pytest -m unit --cov=. --cov-report=term-missing --cov-fail-under=70 -q`
   - `uv run pytest -m integration -q`
5. **Schema spot-check**
   - `psql -c "\dt uns_meta.*"`
   - Validate `uns_meta.metrics` has generated column `canary_id` via `psql -c "\d uns_meta.metrics"`.
6. **CDC publication**
   - `psql -c "SELECT pubname, pubowner FROM pg_publication WHERE pubname = 'uns_meta_pub';"`

## Sign-off
- [ ] Applied & rolled back on staging
- [ ] Test matrix green (unit + integration)
- [ ] Publication validated
- [ ] Checklist archived in release notes
