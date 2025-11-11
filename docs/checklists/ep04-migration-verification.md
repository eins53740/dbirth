# EP-04 Migration Verification Checklist

## Purpose
Use this checklist whenever applying `uns_metadata_sync` migrations in staging or production to confirm schema health and rollback safety.

## Pre-checks
- [ ] PostgreSQL 16.x instance available with owner and app roles provisioned.
- [ ] `wal_level=logical` and replication slots configured as per playbook.
- [ ] Connection string for `uns_meta_owner` verified.
- [ ] Latest artifacts from `main` branch deployed.

## Apply Phase
1. Backup current database or snapshot instance.
2. Run `uv run python -m uns_metadata_sync.migrations apply --conninfo postgresql://uns_meta_owner:OWNER_PW@HOST:PORT/uns_metadata`.
3. Verify CLI output lists migrations in ascending order and ends with "Applied migration 001_release_1_1_schema".
4. Execute verification SQL:
   - `SELECT version, checksum FROM public.schema_migrations ORDER BY version;`
   - `SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'uns_meta';`
   - `SELECT pubname FROM pg_publication WHERE pubname = 'uns_meta_pub';`
5. Capture results and attach to change record.

## Post-apply Smoke Tests
- [ ] Insert sample device/metric rows and confirm `updated_at` auto-updates.
- [ ] Insert metric property with matching enum type.
- [ ] Confirm publication `uns_meta_pub` is active.

## Rollback Drill
- [ ] Execute `uv run python -m uns_metadata_sync.migrations rollback --conninfo ...` in staging.
- [ ] Ensure `uns_meta` schema objects are removed and ledger entry deleted.
- [ ] Re-apply migrations to confirm forward path still succeeds.

## Sign-off
- [ ] Checklist reviewed and signed by DBA/Tech Lead.
- [ ] Artifacts archived in release folder.
