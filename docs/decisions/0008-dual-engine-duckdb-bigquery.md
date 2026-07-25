# ADR-0008: Dual execution engine — BigQuery (documented) + DuckDB (local/CI)

- **Status:** Accepted
- **Date:** 2026-07-25
- **Supersedes part of:** the "BigQuery only" assumption in ADR-0003 (BigQuery
  remains the documented production warehouse; this ADR adds a local engine).

## Context

BigQuery **sandbox** (no billing account) **blocks all DML** — `MERGE`, `UPDATE`,
`DELETE`. Two of the project's non-negotiables need DML:

1. **dbt snapshots** — every run after the first uses `MERGE`.
2. **Incremental `merge`** on `fact_sales` — re-runs use `MERGE`.

The first Bronze→Silver build ran fine on BigQuery (loads + `CREATE TABLE AS` are
not DML), and it reconciled to the penny-ish tie-out. But the snapshot's 2nd run
failed with *"DML queries are not allowed in the free tier."* Enabling billing
would fix it (cost ≈ $0 for MB-scale data), but we wanted the project to run for
anyone, with no billing and no cloud dependency — especially for CI.

## Decision

Run the pipeline on **two engines from one codebase**:

- **BigQuery** stays the **documented production warehouse** (`--target dev`).
- **DuckDB** is the **default local/CI execution engine** (`--target duckdb`),
  which has no DML restriction and no cloud cost.

The SQL is identical across both; only vendor syntax differs, and that is already
isolated behind `macros/warehouse_portability.sql` (per ADR-0003). Concretely:

- `try_cast` maps **logical** types (integer/float/numeric/…) to each engine's
  physical types and null-safe cast function.
- `date_trunc_month`, `month_name`, `day_name`, `is_weekend`, `to_string` wrap the
  handful of vendor-specific date/string functions.
- `fact_sales` picks its incremental strategy by engine:
  `merge` on BigQuery, `delete+insert` on DuckDB — both idempotent on
  `order_line_id`.
- The `raw` source and `generate_schema_name` key off `target.schema` (not the
  BigQuery-only `target.dataset`), so they resolve on both engines.
- `load_to_bronze.py` lands to either engine (`--target`), with the same
  contract gate, metadata, append-only, and content-hash idempotency.

## Consequences

- The **full brief** (snapshots + merge) runs locally with zero cost; verified on
  DuckDB (bronze+silver 71/71, gold 88/88, tie-out, both SCD2 histories,
  point-in-time join, incremental idempotency).
- **CI needs no cloud secrets** (Phase 7) — a major reliability win.
- The portability seam earns its keep: adding DuckDB touched macros + config, not
  the models — evidence the BigQuery→Snowflake path is genuinely cheap.
- Cost: a second code path to keep working. Mitigated by the shared model SQL and
  a single set of tests that run on both.

## Alternatives considered

- **Enable BigQuery billing** — cleanest for a single-engine story, and still the
  recommended route for a real deployment; rejected as the *default* only because
  we wanted no-billing, no-secret reproducibility for any cloner and for CI.
- **Stay on sandbox, drop snapshots + merge** — rejected: guts two stated
  non-negotiables.
- **DuckDB only** — rejected: the role and brief are cloud-warehouse-centric;
  BigQuery must remain the documented target, not be replaced.
