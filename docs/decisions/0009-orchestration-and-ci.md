# ADR-0009: Dagster orchestration and DuckDB-based CI

- **Status:** Accepted
- **Date:** 2026-07-25

## Context

The pipeline needs (a) orchestration that models the ingestion → dbt dependency
and can be scheduled, and (b) CI that lints and runs the whole build+test suite
on every push, failing on any test failure — ideally without cloud secrets.

## Decisions

### 1. Dagster, asset-based, with ingestion as the dbt sources
The Dagster project (`orchestration/definitions.py`) exposes:
- a Python `multi_asset` `land_bronze` that runs the contract-gated loader and
  **produces the five dbt source asset keys**, and
- `@dbt_assets` running `dbt build` (every seed, snapshot, model, and test).

Because `land_bronze` produces the exact asset keys dbt assigns to its sources,
dagster-dbt wires the dependency automatically: ingestion runs first, then every
source-reading model, then tests — one `northwind_pipeline` job on a daily
schedule. This is asset-centric (lineage is first-class) rather than a
task-DAG of opaque scripts.

### 2. CI runs on DuckDB, not BigQuery
GitHub Actions runs the real pipeline on the **DuckDB** target: generate data →
lint → contract-validate + land Bronze → `dbt build` (with the SCD2 snapshot
bootstrap) → tests → source freshness. Because DuckDB needs no credentials, CI
has **no cloud secrets**, runs in ~a minute, and is fully reproducible. An
isolated `northwind_ci` schema and an absolute `DUCKDB_PATH` keep the loader and
dbt pointed at the same database file.

### 3. `cautious` indirect test selection on the split build
CI builds in two dbt invocations (bronze+silver, then snapshots, then
gold+marts). A cross-layer singular test (fact rows vs source rows) references
both a Bronze model and `fact_sales`; dbt's default *eager* selection would run
it during the first build, before `fact_sales` exists. The first build therefore
uses `--indirect-selection cautious` so a test only runs once all its inputs are
built. (Found by running the CI recipe locally before pushing.)

## Consequences

- One scheduled, lineage-aware pipeline; the same `dbt build` runs under Dagster
  and in CI.
- CI is secret-free, fast, deterministic, and gates every push on lint + 195
  tests. Verified locally end-to-end (lint clean, 15 pytest, 91 + 125 dbt nodes).
- The daily Dagster run also re-runs the product snapshot, so SCD2 history
  accumulates going forward — the production-correct behaviour.

## Alternatives considered

- **Airflow** — heavier to run locally, task-centric rather than asset-centric,
  and the dbt integration is less tight than dagster-dbt. Overkill here.
- **BigQuery in CI** — would need a service-account secret in the repo and incur
  the sandbox DML limits (ADR-0008); rejected in favour of the zero-secret DuckDB
  run. BigQuery remains the documented production target.
- **Plain `dbt build` in a cron** — no lineage, no retries/observability, no
  ingestion coupling; Dagster gives all three for little extra code.
