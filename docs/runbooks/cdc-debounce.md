# CDC Debounce Configuration Runbook

This runbook explains how to tune the CDC debounce pipeline so that metric diff
emissions stay within SLA while keeping memory usage bounded. It assumes
familiarity with the architecture described in the design doc
(`docs/Metadata Sync Microservice Solution Design - Release 1.1.md`, CDC
section).

## Overview

The CDC listener batches Postgres logical replication events for each `metric_id`
and emits condensed diffs after a debounce window elapses. Three knobs control
how aggressively we buffer before flushing:

- **Window length** – how long we wait before emitting a diff.
- **Flush interval** – how frequently we check for expired entries.
- **Buffer cap** – the maximum number of distinct metrics we keep pending.

Additional runtime parameters control idle loop sleep, batch size, and where the
replication resume token is persisted.

## Configuration Reference

All values can be supplied via environment variables (preferred) or directly in
`Settings`. Defaults match the design target of a 3-minute debounce window.

| Setting (Settings attr) | Environment variable | Default | Recommended range | Notes |
| --- | --- | --- | --- | --- |
| `cdc_window_seconds` | `CDC_DEBOUNCE_SECONDS` | `180` | 60 – 300 | Larger window improves dedupe but increases latency. |
| `cdc_flush_interval_seconds` | `CDC_FLUSH_INTERVAL_SECONDS` | `5.0` | 1 – 15 | Interval between buffer sweeps; keep < ⅓ of window. |
| `cdc_buffer_cap` | `CDC_BUFFER_CAP` | `1000` | 100 – 5000 | Maximum distinct metrics waiting to flush. |
| `cdc_idle_sleep_seconds` | `CDC_IDLE_SLEEP_SECONDS` | `1.0` | 0.1 – 5 | Sleep duration when no new messages nor flushes. |
| `cdc_max_batch_messages` | `CDC_MAX_BATCH_MESSAGES` | `500` | 100 – 2000 | Upper bound per processing pass; governs checkpoint cadence. |
| `cdc_checkpoint_backend` | `CDC_CHECKPOINT_BACKEND` | `file` | `file` \| `memory` | `file` keeps resume tokens across restarts. |
| `cdc_resume_path` | `CDC_RESUME_PATH` | `cdc_resume_tokens.json` | Any persistent path | Directory must be writable by the service. |
| `cdc_resume_fsync` | `CDC_RESUME_FSYNC` | `false` | `false` \| `true` | Enable only when strict durability is required. |

### Recommended baselines

1. Start with the defaults above in staging and measure:
   - Average latency between source update and diff emission.
   - Number of metrics held in the buffer during peak load.
2. Adjust `cdc_window_seconds` first to meet latency targets.
3. Increase `cdc_buffer_cap` only if warnings indicate capacity drops.

## Metrics and Alerts

The listener exports Prometheus metrics under the namespace
`<namespace>_cdc_*` (defaults to `uns_metadata_sync_cdc_*`). Key signals:

- `uns_metadata_sync_cdc_buffer_depth` (gauge) – current debounce size.
- `uns_metadata_sync_cdc_drops_total` – number of entries dropped due to cap.
- `uns_metadata_sync_cdc_emitted_total` – count of flush cycles.
- `uns_metadata_sync_cdc_records_total` – replication change records processed.
- `uns_metadata_sync_cdc_errors_total` – processing failures.

Alert recommendations:

- Page if `errors_total` increases steadily for >5 minutes.
- Warn if `buffer_depth` remains >80% of `cdc_buffer_cap` for >2 windows.
- Warn if `drops_total` grows at >1/min – indicates buffer cap too small.

## Troubleshooting Matrix

| Symptom | Likely cause | Config to tweak | Suggested action |
| --- | --- | --- | --- |
| Diff latency exceeds SLA | Debounce window too long | `cdc_window_seconds`, `cdc_flush_interval_seconds` | Reduce window by 30s increments; ensure flush interval ≤⅓ of window. |
| Frequent debounce drops logged | Buffer cap too small or burst load | `cdc_buffer_cap`, `cdc_max_batch_messages` | Increase cap by 25% and confirm hardware headroom; optionally raise batch size so checkpoints keep up. |
| Resume after restart replays duplicates | Volatile checkpoint backend | `cdc_checkpoint_backend`, `cdc_resume_path` | Switch backend to `file`, ensure resume path is on persistent volume. |
| Idle CPU usage high during low throughput | Idle sleep too short | `cdc_idle_sleep_seconds` | Increase sleep to 2–3 seconds in low-traffic environments. |
| Lag spikes despite low buffer depth | Flush cadence too sparse | `cdc_flush_interval_seconds` | Lower interval (e.g., 5 → 2) so expired entries emit promptly. |
| Resume file not updating | Path unwritable or fsync blocking | `cdc_resume_path`, `cdc_resume_fsync` | Place file on writable disk; disable fsync unless required. |

## Operational Playbook

1. **Baseline** – capture metrics for at least two full debounce windows after
   deploying changes. Export a Grafana snapshot for review.
2. **Tune window** – adjust `CDC_DEBOUNCE_SECONDS` in 30–60s steps, deploy, and
   remeasure. Maintain a checklist of changes to prevent thrash.
3. **Capacity planning** – during expected peak load, verify
   `buffer_depth < 0.7 * cdc_buffer_cap`. If higher, bump capacity and validate
   memory usage.
4. **Checkpoint hygiene** – ensure `cdc_resume_tokens.json` is part of backup or
   can be recreated safely. For manual resets, use the service API documented
   in TBD-EP-05-IMP-02 and capture the pre-reset LSN.
5. **Post-adjustment verification** – run `uv run pytest -m unit -k debounce` in
   CI to guard against regressions when updating code and documentation.

## Troubleshooting Workflow

1. Confirm the latest settings via the environment (`env | grep CDC_`) or by
   dumping `Settings` in a REPL.
2. Inspect Prometheus metrics for spikes in `buffer_depth`, `drops_total`, and
   `errors_total`.
3. Review service logs around the issue window. The debounce buffer logs a
   warning when dropping entries (`debounce buffer full - dropping metric ...`).
4. Apply adjustments per the matrix above. Record changes in the ops change log.
5. After modifications, validate that the diff latency returns to baseline and
   drops stop increasing.

## References

- `docs/Metadata Sync Microservice Solution Design - Release 1.1.md`
- `src/uns_metadata_sync/cdc/service.py` for metrics implementation
- `src/uns_metadata_sync/config.py` for configuration defaults
