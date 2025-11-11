# PostgreSQL Maintenance Playbook (UNS Metadata Sync)

## Purpose
- Provide an operational checklist for maintaining the UNS metadata PostgreSQL cluster that backs the metadata sync service.
- Ensure backups, vacuum/analyze, TLS asset rotation, and constraint/index validation occur on a predictable cadence.

## Audience
- Platform operations engineers responsible for day-to-day database health.
- DBA reviewers who sign off on schema integrity and security controls.
- On-call engineers who respond to metadata persistence incidents.

## References
- Schema contract, constraints, and ERD: `docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.1).md`
- Operations overview: `docs/Metadata Sync Microservice Solution Design - Release 1.1.md` (see "Operations & Support")
- Migration history and DDL source of truth: `database/migrations/`
- Migration verification procedure: `docs/runbooks/migration-verification-release-1.1.md`

---

## Cluster Overview
- **Environment**: PostgreSQL 16 (managed in Secil private cloud)
- **Primary schema**: `uns_meta` inside database `uns_metadata`
- **Roles**:
  - `uns_meta_admin` - superuser equivalent for maintenance (minimal usage)
  - `uns_meta_app` - service account for application writes (restricted to schema)
  - `uns_meta_ro` - reporting/analytics read-only role
  - `uns_meta_cdc` - logical replication slot owner (`uns_meta_slot`)
- **TLS**:
  - Incoming connections require TLS 1.3 with `verify-full`
  - Certificates stored in secrets manager entries `postgres/uns_metadata/<env>/client`
  - Rotation cadence: every 180 days or when triggered by key compromise

---

## Maintenance Cadence Checklist

### Daily
- [ ] Confirm backup job success (check `pgbackrest` or managed backup dashboard)
- [ ] Review `pg_stat_database` for abnormal `deadlocks`, `blk_read_time`, `blk_write_time`
- [ ] Verify CDC slot lag with `SELECT pg_catalog.pg_current_wal_lsn() - restart_lsn FROM pg_replication_slots WHERE slot_name = 'uns_meta_slot';`
- [ ] Ensure TLS certificates have >14 days validity (`openssl x509 -enddate`) - alert if nearing expiry

### Weekly
- [ ] Run targeted `VACUUM (VERBOSE, ANALYZE)` on `uns_meta.metric_properties` and `uns_meta.metric_versions`
  ```sql
  VACUUM (VERBOSE, ANALYZE) uns_meta.metric_properties;
  VACUUM (VERBOSE, ANALYZE) uns_meta.metric_versions;
  ```
- [ ] Regenerate index statistics for high-write tables:
  ```sql
  ANALYZE VERBOSE uns_meta.devices;
  ANALYZE VERBOSE uns_meta.metrics;
  ```
- [ ] Capture constraint/index health snapshot (see [Validation SQL](#validation-sql-kit)) and archive under `/var/log/uns-meta/db-checks/YYYY-MM-DD/`

### Monthly
- [ ] Review storage trends (`pg_total_relation_size`) and adjust autovacuum thresholds if table bloat >15%
- [ ] Validate role grants against design baseline (no privilege drift)
- [ ] Rotate TLS certificates if within 30 days of expiry; notify service owners and deploy updated secrets
- [ ] Test point-in-time recovery (PITR) on staging snapshot; document results

### Quarterly
- [ ] Conduct full disaster recovery rehearsal (restore to isolated environment, run integration smoke from `docs/runbooks/migration-verification-release-1.1.md`)
- [ ] Review and renew firewall rules, connection pool sizing, and failover configuration
- [ ] Audit replication slot retention and confirm no orphaned WAL segments accumulate

---

## TLS Key Rotation Procedure
1. **Prepare certificates**: Request new client cert/key via corporate PKI (`postgres/uns_metadata/<env>/client`). Confirm CN matches `uns_metadata` host and SAN contains cluster endpoints.
2. **Update secrets**: Upload cert and key to secrets manager entry consumed by metadata sync service and maintenance tooling.
3. **Staged deployment**:
   - Redeploy maintenance scripts or cron jobs that connect using TLS with new certs.
   - Schedule service restart (metadata sync) outside ingest windows; ensure `DB_MODE` toggles remain `local`.
4. **Validation**:
   - From bastion host, run `psql "sslmode=verify-full sslrootcert=root.pem sslcert=new.crt sslkey=new.key" -c 'SELECT current_user;'`.
   - Confirm application logs show successful reconnect without TLS errors.
5. **Revoke old cert**: Mark previous cert as revoked in PKI and purge from disk.

---

## Validation SQL Kit

### Constraints
```sql
-- Detect disabled or invalid constraints in uns_meta schema
SELECT conrelid::regclass AS table_name,
       conname,
       contype,
       CASE WHEN convalidated THEN 'valid' ELSE 'needs revalidate' END AS status
FROM pg_constraint
WHERE connamespace = 'uns_meta'::regnamespace
ORDER BY status DESC, table_name;
```

```sql
-- Verify CHECK constraint coverage for metric properties storage columns
SELECT conname,
       pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname LIKE 'chk_metric_properties_%';
```

### Indexes
```sql
-- Surface missing or invalid indexes
SELECT indexrelid::regclass AS index_name,
       indisvalid,
       indisready,
       pg_relation_size(indexrelid) AS index_bytes
FROM pg_index
JOIN pg_class idx ON idx.oid = indexrelid
WHERE idx.relnamespace = 'uns_meta'::regnamespace
ORDER BY indisvalid, indisready;
```

```sql
-- Validate uniqueness enforcement matches schema contract
SELECT relname, pg_get_indexdef(indexrelid)
FROM pg_index
JOIN pg_class tbl ON tbl.oid = indrelid
WHERE tbl.relnamespace = 'uns_meta'::regnamespace
  AND indisunique;
```

### Vacuum & Bloat
```sql
-- Monitor table bloat using pg_stat_all_tables and pgstattuple (extension required)
SELECT relname,
       n_dead_tup,
       vacuum_count,
       autovacuum_count
FROM pg_stat_all_tables
WHERE schemaname = 'uns_meta'
ORDER BY n_dead_tup DESC;
```

```sql
-- Assess bloat percentage (requires pgstattuple)
SELECT relname,
       round(100 * (1 - tuple_percent / 100)::numeric, 2) AS bloat_pct
FROM pgstattuple('uns_meta.metric_properties');
```

---

## Troubleshooting Flows

### Flow A - Constraint Violation During Ingest
1. **Alert intake**: Application logs (`constraint_violation` metric) or Sentry issue.
2. **Identify offending payload**: Extract `device_id`, `metric_id`, or `uns_path` from log context.
3. **Run constraint validation query** (see [Constraints](#validation-sql-kit)); confirm which constraint failed.
4. **Check upstream schema contract**: Compare payload against `docs/Metada Sync Microservice - PostgreSQL Schema & ERD (Release 1.1).md` expected types.
5. **Mitigation**:
   - If data issue: coordinate with upstream to correct payload; re-run ingest using `scripts/ingest_fixture.py`.
   - If schema drift: halt ingest by setting `DB_MODE=mock`, apply migration or fix constraint as per change control.
6. **Recover**: Re-enable ingest, monitor `tests/integration/test_repository_upserts_db.py` in CI for regression coverage.

### Flow B - TLS Handshake Failures
1. **Detection**: `psycopg.OperationalError` showing `certificate verify failed` or `expired`.
2. **Validate cert**: `openssl x509 -in client.crt -noout -enddate`.
3. **Check secrets**: Ensure new cert and key stored under the correct secret path, permissions `600`.
4. **Rotate**: Follow [TLS Key Rotation Procedure](#tls-key-rotation-procedure).
5. **Post-rotation**: Review application metrics `db_connection_errors_total`. If errors persist, verify CA bundle and server certificate chain availability.

### Flow C - Vacuum Autovacuum Lag
1. **Detection**: Grafana alert on `n_dead_tup` > 5M or `autovacuum_count` stagnant for 24h.
2. **Inspect**: Run bloat queries; confirm autovacuum worker activity via `SELECT * FROM pg_stat_activity WHERE query LIKE 'autovacuum%';`
3. **Manual Intervention**:
   ```sql
   SET maintenance_work_mem = '2GB';
   VACUUM (FULL, ANALYZE) uns_meta.metric_properties;
   ```
4. **Tune**: Adjust `autovacuum_vacuum_cost_limit`, `autovacuum_naptime` for target tables in `postgresql.conf`.
5. **Follow-up**: Document adjustments in change log; verify no replication lag introduced.

---

## Backup and Recovery Notes
- Nightly backups use `pgbackrest` differential policy; full backups occur each Sunday.
- PITR target: <15 minutes data loss, <30 minutes restore time on primary.
- To validate backup integrity:
  ```bash
  pgbackrest --stanza=uns-meta check
  pgbackrest --stanza=uns-meta info
  ```
- Recovery rehearsal steps:
  1. Provision staging instance with identical extensions.
  2. Restore latest backup (`pgbackrest --stanza=uns-meta restore --delta`).
  3. Apply latest migrations from `database/migrations`.
  4. Run application smoke tests (`pytest tests/integration/test_repository_upserts_db.py -k smoke`).

---

## Change Management
- Maintenance that impacts availability must follow the platform RFC process and receive DBA sign-off.
- For vacuum/full rebuild operations on large tables (>10 GB), schedule during off-peak ingestion windows.
- Log all maintenance actions in the `#uns-meta-ops` Slack channel with start/stop times and outcomes.

---

## Appendix
- Related documents: see [References](#references).
- Point of contact for DBA review: `dba@secil.pt`.
- Ensure this playbook is reviewed annually or after material schema or infrastructure changes.
