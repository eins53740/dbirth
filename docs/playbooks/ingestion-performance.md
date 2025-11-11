## Ingestion Performance: `upsert_metric_properties_bulk` (Remote vs Local)

This note investigates why `upsert_metric_properties_bulk` took ~6+ hours on the remote server while the same workload completes in ~80 seconds locally.

Observed run (remote):
- Fixture: `messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json`
- Devices: 1
- Metrics: 98,332
- Properties: 830,605
- Timings (s): `upsert_metric_properties_bulk: 21998.747` (~6.11 hours)

Observed run (local):
- The same fixture completes in ~80 seconds end-to-end.

The disparity strongly suggests an environmental and workload interaction problem rather than purely application code. Below are likely root causes, how to confirm, and practical fixes.

---

### Likely Root Causes (ranked)

1) Per-transaction fsync amplification (small commits or autocommit)
- Symptom: Many INSERT/UPSERT statements each incurring a WAL flush/commit.
- On a remote EC2 host with modest IOPS, per-transaction fsync costs dominate, multiplying by property count and batch count.
- Local runs often benefit from very fast storage, fewer network hops, and cached filesystem buffers, masking this cost.

2) CPU credit throttling on `t3.medium` (burstable CPU)
- `t3.medium` has limited CPU credits. Long, CPU-heavy write workloads (UPSERTs touching indexes) can quickly exhaust credits.
- Once credits are depleted, the instance is throttled for hours, turning minutes-long tasks into multi-hour runs.

3) I/O-constrained storage for WAL/index updates
- If the PostgreSQL data volume is gp2 with small size (low baseline IOPS) or otherwise limited throughput/IOPS, WAL fsyncs and index updates become the bottleneck.
- Heavy `ON CONFLICT DO UPDATE` paths write significantly more than plain INSERTs (read + write + index churn), exacerbating I/O pressure.

4) Many or heavy indexes on the properties table (e.g., GIN on JSONB)
- Each insert/update updates all indexes. Wide JSONB columns plus GIN/GiST indexes are expensive to maintain.
- If most rows hit the UPDATE path (conflict), HOT updates may not apply, causing more index rewrites.

5) Suboptimal conflict target or missing supporting index
- `ON CONFLICT (...) DO UPDATE` must match a UNIQUE/PK index. If the conflict target doesn’t exactly match the index (including types/expressions), Postgres does extra work.

6) Foreign key checks without indexes
- If the properties table references other tables and those FK target columns lack indexes, each insert/update can scan the referenced table.

7) Row-level triggers or RLS
- Per-row triggers or policies dramatically slow bulk writes.

8) Network round-trips and small batch size from the client
- If the client uses small batches or per-row statements in autocommit, network latency and per-commit fsync dominate.

---

### How To Confirm

Database visibility
- Enable pg_stat_statements (if not already): confirm the top time-consuming statements and their call counts.
  - Check: `SHOW shared_preload_libraries;` → must include `pg_stat_statements`.
  - View: `SELECT total_time, mean_time, calls, query FROM pg_stat_statements ORDER BY total_time DESC LIMIT 20;`
- Inspect background writer and checkpoints: `SELECT * FROM pg_stat_bgwriter;`
  - Look for frequent checkpoints or high `buffers_checkpoint` / `buffers_backend_fsync`.
- Per-database stats: `SELECT * FROM pg_stat_database WHERE datname = current_database();`
- Lock contention: `SELECT * FROM pg_locks WHERE NOT granted;`

Schema/index checks
- Describe the properties table and indexes:
  - `\d+ your_schema.metric_properties`
  - Ensure the UNIQUE/PK index exactly matches the `ON CONFLICT` target.
- Count and type of indexes (GIN on JSONB?): heavy indexes slow bulk upserts.
- FK presence and index coverage on referenced columns.

Explain the UPSERT path
- Run a representative `EXPLAIN (ANALYZE, BUFFERS)` of the UPSERT using a small sample and verify the conflict lookup is using the intended unique index.

System/infra
- CPU credits: check `cloudwatch` metrics `CPUCreditBalance` and `CPUSurplusCreditsCharged` for the instance during the ingest window.
- Disk IOPS/throughput: check volume type/size and CloudWatch `VolumeWriteOps`, `VolumeWriteBytes`, `VolumeQueueLength`.
- OS fsync latency: `pg_stat_bgwriter` and `iostat` (Linux) can help; look for high await on the data volume.

Client behavior
- Confirm batch sizes and transaction boundaries in the ingestion code:
  - Is `autocommit` ON? Is the code committing per batch or per row?
  - What batch size is used for properties (e.g., 100, 1,000, 10,000)?
  - Is the code using COPY, `execute_values`, or per-row `execute`?

---

### High-Impact Fixes (tactical)

Client/session-level
- Use a single transaction for the entire bulk load or large chunks. Ensure `autocommit = False`.
- Set `SET LOCAL synchronous_commit = off;` for the ingest session to avoid per-commit fsync stalls.
- Use larger batches and fewer round-trips:
  - Prefer `COPY` into a staging table over many inserts.
  - If staying with INSERT, use `psycopg.extras.execute_values` with `page_size` in thousands (e.g., 5k–20k) rather than hundreds.
  - Avoid per-row `execute` calls.

Staging + MERGE (recommended)
- Pattern:
  1) `CREATE TEMP TABLE tmp_properties (LIKE metric_properties INCLUDING ALL) ON COMMIT DROP;`
  2) `COPY tmp_properties FROM STDIN CSV` (or binary) from the client.
  3) `INSERT INTO metric_properties (...) SELECT ... FROM tmp_properties ON CONFLICT (...) DO UPDATE SET ...;`
  4) Wrap steps 2–3 in a single transaction, with `synchronous_commit = off`.
- Benefits: minimal network chatter, optimized WAL patterns, conflict checks happen once in a single statement.

Reduce index and trigger overhead during load
- If possible, drop or disable heavy secondary indexes (e.g., JSONB GIN) and triggers before the load and recreate them after.
  - Alternatively, target only the essential unique/PK index during load.
  - Recreate indexes concurrently post-load to avoid long locks.

Data-level optimizations
- Deduplicate properties client-side before sending: if repeated updates of the same (metric_id, key) occur in the same batch, consolidate to the final value.
- Avoid unnecessary updates: on conflict, only update when the incoming value differs (`WHERE EXCLUDED.val <> metric_properties.val`).

---

### Database/Infra Tuning (strategic)

Instance sizing
- Use a non-burstable family (e.g., `m6i.large`/`c7i.large`) or enable Unlimited mode for T-class to avoid credit throttling.
- Provision more RAM (≥8 GB) to raise `shared_buffers` and caching effects.

Storage
- Prefer gp3 with explicit IOPS/throughput sizing appropriate for WAL-heavy loads (e.g., 6k+ IOPS and ≥250 MB/s throughput for large ingest windows).
- Ensure the WAL directory and data directory aren’t on extremely low IOPS volumes.

PostgreSQL config (safe defaults for bulk ingest)
- `shared_buffers`: ~25% of RAM (e.g., 1–2 GB on 8 GB host).
- `checkpoint_timeout`: 15–30 min; `max_wal_size`: increase to reduce checkpoint frequency; `checkpoint_completion_target`: 0.9.
- `wal_compression = on` (often beneficial for large WAL).
- `maintenance_work_mem`: increase during index builds (e.g., 512 MB–1 GB if RAM allows).
- `effective_io_concurrency` and `random_page_cost`: tune for SSD.

Operational toggles during ingest
- For the ingest session only: `SET LOCAL synchronous_commit = off;` (safe if you can tolerate loss of the last transaction on crash).
- Consider `UNLOGGED` staging tables to reduce WAL.
- Build heavy secondary indexes after the load.

---

### Code-Level Recommendations (concrete)

If the current implementation uses per-row or small-batch UPSERTs:
- Ensure one transaction per phase:
  - Disable autocommit; begin transaction before bulk; commit after.
- Enable fast path:
  - `cursor.execute("SET LOCAL synchronous_commit = off;")`
  - If using psycopg3, consider `conn.execute("SET LOCAL synchronous_commit = off")` once per transaction.
- Use `execute_values` for UPSERT batches if not using COPY:
  - Example: `execute_values(cur, "INSERT INTO metric_properties (...) VALUES %s ON CONFLICT (...) DO UPDATE SET ...", rows, page_size=10000)`
- Or switch to COPY + MERGE:
  - Copy to temp/staging table, then single `INSERT ... ON CONFLICT DO UPDATE` from staging.

Avoid unnecessary writes:
- On conflict update, add a WHERE clause to update only if the value differs to reduce index churn and WAL:
  - `... DO UPDATE SET value = EXCLUDED.value WHERE metric_properties.value IS DISTINCT FROM EXCLUDED.value;`

Batch sizing guideline:
- Start with `10k` rows per statement (or per COPY chunk) and adjust based on memory and server feedback.

---

### Verification Plan

1) Instrument
- Enable `pg_stat_statements` and set `log_min_duration_statement = 1000` (1s) during a test run.
- Capture: number of commits (`xact_commit`), checkpoints, and total WAL generated (`pg_stat_wal_lsn_diff` if available).

2) A/B tests
- Baseline: current approach.
- Test A: Single transaction + `synchronous_commit = off` + larger batches (10k).
- Test B: COPY to staging + single MERGE (`INSERT ... ON CONFLICT`).
- Compare wall-clock times and WAL volume.

3) Infra
- Monitor CPU credits, CPU utilization, disk IOPS/throughput during the run. If credits drop to 0 or disk queues spike, that’s your bottleneck.

---

### TL;DR (Actionable Steps)

1) Ensure ingestion runs in one transaction with `synchronous_commit = off`.
2) Use larger batches or COPY into a staging table and merge in one statement.
3) Reduce or defer heavy secondary indexes/triggers during the bulk load.
4) Verify the conflict target has an exact matching UNIQUE/PK index.
5) Check t3 CPU credits and EBS IOPS; consider a non-burstable instance or gp3 with higher IOPS for ingestion.
6) Log and analyze with `pg_stat_statements` to validate improvements.

---

### Appendix: Example SQL Patterns

Session-safe toggles
```sql
BEGIN;
SET LOCAL synchronous_commit = off;
-- Bulk work ...
COMMIT;
```

COPY into staging and merge
```sql
BEGIN;
SET LOCAL synchronous_commit = off;

CREATE TEMP TABLE tmp_properties (LIKE metric_properties INCLUDING ALL) ON COMMIT DROP;
-- client: COPY FROM STDIN (CSV or binary)

INSERT INTO metric_properties AS mp (metric_id, key, value, updated_at)
SELECT metric_id, key, value, updated_at
FROM tmp_properties t
ON CONFLICT (metric_id, key)
DO UPDATE SET value = EXCLUDED.value,
              updated_at = EXCLUDED.updated_at
WHERE mp.value IS DISTINCT FROM EXCLUDED.value;

COMMIT;
```

Psycopg `execute_values` batch upsert
```python
from psycopg.extras import execute_values

rows = [(m_id, key, val, ts) for ...]
with conn, conn.cursor() as cur:  # one transaction
    cur.execute("SET LOCAL synchronous_commit = off")
    sql = (
        "INSERT INTO metric_properties (metric_id, key, value, updated_at) VALUES %s "
        "ON CONFLICT (metric_id, key) DO UPDATE SET "
        "value = EXCLUDED.value, updated_at = EXCLUDED.updated_at "
        "WHERE metric_properties.value IS DISTINCT FROM EXCLUDED.value"
    )
    execute_values(cur, sql, rows, page_size=10000)
```
