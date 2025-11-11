# PostgreSQL Local Setup Playbook

## Overview
This playbook explains how to provision a fresh PostgreSQL instance for the UNS Metadata Sync service, apply the release 1.1 schema, and validate the installation on a local workstation.

## 1. Prerequisites
- PostgreSQL 16 installed locally with the `psql` CLI available (Windows default: `C:/Program Files/PostgreSQL/16/bin/psql.exe`).
- Python 3.13 and the `uv` package manager (run `pip install uv` if not already present).
- Project dependencies bootstrapped via `uv venv --python 3.13` and `uv sync --locked --all-extras --dev`.
- Network access to download Python wheels the first time you run `uv sync`.

> Tip: On Windows add `C:/Program Files/PostgreSQL/16/bin` to your `PATH`, or reference the full path to `psql.exe` in the commands below.

## 2. Create Roles and Database
Assign secure secrets for the service accounts and run the commands below with a Postgres superuser (typically `postgres`).

### PowerShell
```powershell
$Env:PGPASSWORD = '<postgres_admin_password>'
$psql = 'C:/Program Files/PostgreSQL/16/bin/psql.exe'

# Create login roles
& $psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE uns_meta_owner LOGIN PASSWORD '<owner_pw>' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;"
& $psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE uns_meta_app   LOGIN PASSWORD '<app_pw>'   NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;"
& $psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE uns_meta_cdc   LOGIN PASSWORD '<cdc_pw>'   NOSUPERUSER NOCREATEDB NOCREATEROLE REPLICATION;"

# Create the database owned by the service owner
& $psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE uns_metadata OWNER uns_meta_owner;"

# Optional grants for app + CDC connections
$sql = @"
GRANT CONNECT ON DATABASE uns_metadata TO uns_meta_app;
GRANT CONNECT ON DATABASE uns_metadata TO uns_meta_cdc;
@";
& $psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -c $sql
```

### Bash
```bash
export PGPASSWORD='<postgres_admin_password>'
psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 <<'SQL'
CREATE ROLE uns_meta_owner LOGIN PASSWORD '<owner_pw>' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE uns_meta_app   LOGIN PASSWORD '<app_pw>'   NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE uns_meta_cdc   LOGIN PASSWORD '<cdc_pw>'   NOSUPERUSER NOCREATEDB NOCREATEROLE REPLICATION;
SQL
psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE uns_metadata OWNER uns_meta_owner;"
psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 <<'SQL'
GRANT CONNECT ON DATABASE uns_metadata TO uns_meta_app;
GRANT CONNECT ON DATABASE uns_metadata TO uns_meta_cdc;
SQL
```

### Interactive bootstrap script (psql)
A helper script is available at `scripts/postgres_bootstrap.sql`. It prompts for the role passwords and idempotently creates the roles, database, and base grants.

```powershell
# Run from the project root
$Env:PGPASSWORD = '<postgres_admin_password>'
psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -f scripts/postgres_bootstrap.sql
```

## 3. Configure PostgreSQL for CDC
- Edit `postgresql.conf` and set `wal_level = logical` (restart the PostgreSQL service afterwards).
- Ensure `max_wal_senders` and `max_replication_slots` have capacity for CDC clients (the default 10 is fine for local work).

Verify:
```sql
SHOW wal_level;
```
The command should return `logical`.

## 4. Update Project Environment
Edit `.env` (or export env vars in your shell) with the new credentials:

```ini
PGHOST=localhost
PGPORT=5432
PGDATABASE=uns_metadata
PGUSER=uns_meta_app
PGPASSWORD=<app_pw>
PGREPLUSER=uns_meta_cdc
PGREPLPASSWORD=<cdc_pw>
DB_MODE=local
```

## 5. Apply Database Migrations
Run the migration CLI with the owner credentials. Add `--dry-run` if you only want to see the pending migrations.

```powershell
$Env:DB_MODE = 'local'
uv run python -m uns_metadata_sync.migrations apply --conninfo "postgresql://uns_meta_owner:<owner_pw>@localhost:5432/uns_metadata"
```

### Verification
```sql
SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'uns_meta' ORDER BY tablename;
SELECT version, checksum FROM public.schema_migrations ORDER BY version;
SELECT pubname FROM pg_publication WHERE pubname = 'uns_meta_pub';
```
All five tables (`devices`, `metrics`, `metric_properties`, `metric_versions`, `metric_path_lineage`) should be present and the publication `uns_meta_pub` should exist.

## 6. Run the Test Suites
Ensure you are inside the project virtual environment and set `DB_MODE=local` before running the test commands.

```powershell
$Env:DB_MODE = 'local'
$Env:PGHOST = 'localhost'
$Env:PGPORT = '5432'
$Env:PGDATABASE = 'uns_metadata'
$Env:PGUSER = 'postgres'      # integration suite needs admin rights today
$Env:PGPASSWORD = '<postgres_admin_password>'

uv run pytest -m unit -v --cov=. --cov-report=term-missing --cov-fail-under=70
uv run pytest -m integration -q
uv run pytest tests/integration/test_migrations_rollback.py -q
```

> The unit suite enforces 70% coverage; expect the run to fail if coverage dips below the threshold. Investigate missing tests before proceeding.

## 7. Troubleshooting
- `psql: not recognized`: add the PostgreSQL `bin` directory to `PATH` or reference the full `psql.exe` path.
- `permission denied to create database`: the integration tests currently connect with `PGUSER=postgres`. Update the env vars before running the suite, or grant `CREATEDB` to your app role if you prefer.
- `wal_level` remains `replica`: double-check you edited the correct `postgresql.conf` and restart Postgres.
- Migrations CLI still no-ops: verify you are running with the owner connection string and check the application logs for SQL errors.
- For missing permissions to create databases run:
```sql
ALTER ROLE uns_meta_owner WITH CREATEDB REPLICATION;
GRANT pg_signal_backend TO uns_meta_owner;
CREATE EXTENSION IF NOT EXISTS wal2json;
```



## psql bootstrap script:
```
\set ON_ERROR_STOP on
\echo 'UNS Metadata Sync PostgreSQL bootstrap'

\prompt 'Owner role password: ' owner_pw
\prompt 'Application role password: ' app_pw
\prompt 'CDC role password: ' cdc_pw

DO $bootstrap$
BEGIN
  PERFORM 1 FROM pg_roles WHERE rolname = 'uns_meta_owner';
  IF NOT FOUND THEN
    EXECUTE format('CREATE ROLE uns_meta_owner LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :owner_pw);
  ELSE
    EXECUTE format('ALTER ROLE uns_meta_owner WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :owner_pw);
  END IF;

  PERFORM 1 FROM pg_roles WHERE rolname = 'uns_meta_app';
  IF NOT FOUND THEN
    EXECUTE format('CREATE ROLE uns_meta_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :app_pw);
  ELSE
    EXECUTE format('ALTER ROLE uns_meta_app WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :app_pw);
  END IF;

  PERFORM 1 FROM pg_roles WHERE rolname = 'uns_meta_cdc';
  IF NOT FOUND THEN
    EXECUTE format('CREATE ROLE uns_meta_cdc LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE REPLICATION', :cdc_pw);
  ELSE
    EXECUTE format('ALTER ROLE uns_meta_cdc WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE REPLICATION', :cdc_pw);
  END IF;
END
$bootstrap$;

SELECT 'CREATE DATABASE uns_metadata OWNER uns_meta_owner'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'uns_metadata');
\gexec

ALTER DATABASE uns_metadata OWNER TO uns_meta_owner;

GRANT CONNECT ON DATABASE uns_metadata TO uns_meta_app;
GRANT CONNECT ON DATABASE uns_metadata TO uns_meta_cdc;
```
