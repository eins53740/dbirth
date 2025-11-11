# UNS Metadata Sync Service

Run the Sparkplug B metadata subscriber via:

```bash
python -m uns_metadata_sync
```

The package uses a .env file for MQTT connection details. Override defaults with the environment variables described in src/uns_metadata_sync/config.py.

## Database Migrations – Why and When

This service persists Sparkplug metadata to Postgres. The database objects it relies on (schema, tables, constraints, triggers, publication for CDC) are created and evolved via SQL migrations that live under `src/uns_metadata_sync/migrations/sql`.

Why we need them
- Define the storage contract used by the service: `uns_meta.devices`, `uns_meta.metrics`, and `uns_meta.metric_properties` plus indexes and `updated_at` triggers.
- Enforce data integrity (unique identities, typed metric properties, cascade rules).
- Publish change streams (logical replication publication `uns_meta_pub`) for downstream consumers (e.g., historian).

When they are applied
- Local development: you apply migrations once to your local Postgres before running the service with `DB_MODE=local`.
- CI: migrations are validated offline on every PR (syntax + presence) and exercised in integration tests against an ephemeral Postgres.
- Release/Deploy: whenever a new version of the service ships with a new numbered migration, apply them to target environments during rollout.

What does not happen automatically
- The subscriber does not auto-run migrations on startup. Treat migrations as part of environment provisioning; run them before switching the service to database mode.

How to run
1) Set owner connection (the role that owns the `uns_metadata` database):
   ```bash
   export DB_MODE=local
   export PGHOST=localhost
   export PGPORT=5432
   export PGDATABASE=uns_metadata
   export PGUSER=uns_meta_owner
   export PGPASSWORD=***owner_password***
   ```
2) Dry run to see what would apply:
   ```bash
   uv run python -m uns_metadata_sync.migrations apply --dry-run
   ```
3) Apply for real:
   ```bash
   uv run python -m uns_metadata_sync.migrations apply
   ```

Verification
- Check tables and the migration ledger:
  ```bash
  psql "$PGUSER://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE" -c "SELECT version, checksum FROM public.schema_migrations ORDER BY version;"
  psql "$PGUSER://$PGUSER:$PGUSER@$PGHOST:$PGPORT/$PGDATABASE" -c "SELECT schemaname, tablename FROM pg_tables WHERE schemaname='uns_meta' ORDER BY tablename;"
  psql "$PGUSER://$PGUSER:$PGUSER@$PGHOST:$PGPORT/$PGDATABASE" -c "SELECT pubname FROM pg_publication WHERE pubname='uns_meta_pub';"
  ```

Rollback (staging drill only)
```bash
uv run python -m uns_metadata_sync.migrations rollback --dry-run   # see what would roll back
uv run python -m uns_metadata_sync.migrations rollback             # execute one step back
```

Troubleshooting
- “Applied migration … but nothing changed”: ensure you are connecting with the owner role and the correct database; re-run without `--dry-run`.
- Permission errors in integration tests: those tests create/drop temporary databases; run them with an administrative user (e.g., `PGUSER=postgres`) or grant `CREATEDB` to your test role.
- CDC unavailable: confirm `wal_level=logical` and that `uns_meta_pub` exists.
