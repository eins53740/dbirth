---
title: DBIRTH Ingest Performance (Local Run)
date: 2025-10-08
status: draft
---

Summary
- Fixture: real Sparkplug DBIRTH JSON (messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json)
- Command: uv run python scripts/ingest_fixture.py --conninfo "host=localhost port=5432 dbname=uns_metadata user=postgres password=****" --fixture messages_spBv1.0_Secil_DBIRTH_Portugal_Cement.json
- Result: Ingest complete: devices=1, metrics=98,332, properties=830,605
- Duration: ~10 minutes (local developer machine)
- Throughput (approx):
  - Metrics: ~164 metrics/sec
  - Properties: ~1,384 props/sec

Environment
- Postgres: local (default settings), db=uns_metadata
- Schema: Release 1.1 migrations applied
- Python: psycopg 3, synchronous connection
- Script: scripts/ingest_fixture.py (device + metrics + typed metric_properties upserts)

Observed Bottlenecks
- Per-row upsert pattern (device/metric/property) incurs multiple round trips:
  - Lookup + insert/update per metric
  - Lookup + insert/update per property
  - Nested transactions (repo methods wrap each call in a transaction) → savepoint overhead across tens/hundreds of thousands of rows
- Single-row statements prevent the planner from optimizing IO; high parse/plan overhead
- JSON parsing is not dominant; DB interaction dominates wall time

Optimization Strategies (prioritized)
1) Batch upserts with ON CONFLICT (most leverage)
   - Metrics: single multi-row insert with ON CONFLICT (device_id, name) DO UPDATE SET uns_path = EXCLUDED.uns_path, datatype = EXCLUDED.datatype RETURNING metric_id
     - Eliminates pre-lookup by uns_path and the identity select/update dance
   - Properties: multi-row insert with ON CONFLICT (metric_id, key) DO UPDATE SET type = EXCLUDED.type, value_* = EXCLUDED.value_* RETURNING metric_id, key
   - Apply in chunks (e.g., 5k metrics / 25k props) to keep statement size manageable

2) Caller-managed transactions (avoid nested savepoints)
   - Wrap ingest in one outer transaction per batch; repo methods should support a mode that skips internal conn.transaction() usage
   - Benefit: removes thousands of savepoints and reduces fsyncs to one per batch

3) COPY to staging + merge
   - Create UNLOGGED staging tables: staging_metrics(staging_id, device_id, name, uns_path, datatype), staging_props(...)
   - COPY (binary) the batch into staging, then perform 1–2 set-based MERGE/INSERT…ON CONFLICT into base tables
   - Fastest path on Postgres; minimizes client/server chattiness and WAL

4) Session settings for bulk ingest
   - SET LOCAL synchronous_commit = off (within the ingest transaction)
   - SET LOCAL maintenance_work_mem and work_mem higher if RAM allows
   - Consider temporarily disabling autovacuum on staging tables

5) Statement-level improvements
   - Use prepared statements or keep a single cursor with repeated execs
   - Avoid dict_row row factory for bulk paths (tuple rows are faster)
   - Reduce RETURNING payload to only required columns

6) Parallelism (after batching is in place)
   - Partition work by metric batches and run 2–4 workers (processes) each with its own transaction
   - Keep deterministic order to avoid deadlocks; shard by metric name hash or by contiguous slices

Proposed SQL patterns
- Metrics (batch):
  INSERT INTO uns_meta.metrics (device_id, name, uns_path, datatype)
  VALUES %s
  ON CONFLICT (device_id, name) DO UPDATE
    SET uns_path = EXCLUDED.uns_path,
        datatype = EXCLUDED.datatype
  RETURNING metric_id, device_id, name;

- Properties (batch):
  INSERT INTO uns_meta.metric_properties (
    metric_id, key, type, value_int, value_long, value_float, value_double, value_string, value_bool
  ) VALUES %s
  ON CONFLICT (metric_id, key) DO UPDATE SET
    type = EXCLUDED.type,
    value_int = EXCLUDED.value_int,
    value_long = EXCLUDED.value_long,
    value_float = EXCLUDED.value_float,
    value_double = EXCLUDED.value_double,
    value_string = EXCLUDED.value_string,
    value_bool = EXCLUDED.value_bool
  RETURNING metric_id, key;

Estimated Impact
- Replace per-row logic with batched ON CONFLICT: 5–15x reduction in round trips
- COPY + merge: typically 10–30x faster vs per-row for >100k rows
- Disabling nested transactions: ~1.5–3x improvement depending on batch size
- Combined: Expected end-to-end time for 98k/830k scale to drop from ~10m to ~1–3m on a laptop-class machine

Implementation Plan
- v1: Add BulkWriter with execute_values (metrics/properties) + caller-managed transaction
- v2: Add staging tables + COPY path (feature-flagged), keep v1 as fallback
- v3: Optional parallel workers (configurable), with batch size and worker count tuning

Validation
- Re-run fixture ingest and capture timings per phase (parse, metrics upsert, props upsert)
- Verify row counts and spot-check values (existing integration verification queries)
- Confirm constraints remain satisfied (no dup uns_path, PK/UK intact)

Notes
- Lineage/version writes can be appended post-upsert; for performance, compute diffs in memory and batch write lineage/version where feasible
- Maintain idempotency guarantees: batching should not change semantics; ON CONFLICT ensures deterministic outcomes
