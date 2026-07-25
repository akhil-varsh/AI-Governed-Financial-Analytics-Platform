# Why — Phase 7: Orchestration and CI

Interview-defensible notes for the operational layer.

## "How does Dagster know to run ingestion before dbt?"

The clean dagster-dbt way: my Python ingestion `multi_asset` (`land_bronze`)
**produces the same asset keys that dbt assigns to its sources**. So when
dagster-dbt builds the graph, every model that reads a raw source is
automatically downstream of `land_bronze` — no manual ordering, no glue. The DAG
becomes land_bronze → bronze views → silver → gold (+ snapshot) → marts, with dbt
tests as asset checks along the way. One job, one daily schedule.

## "Why is CI on DuckDB instead of BigQuery?"

Two reasons. First, **no secrets**: DuckDB needs no credentials, so CI doesn't
carry a service-account key and can't leak one. Second, the BigQuery sandbox
blocks the DML that snapshots and merge need (ADR-0008), so it couldn't run the
full build anyway. CI generates the data, lints, validates + lands Bronze, runs
the whole `dbt build` including the SCD2 snapshot bootstrap, runs all 195 tests,
and checks source freshness — in about a minute, deterministically. BigQuery
stays the documented production target; DuckDB is where verification runs.

## "Walk me through a CI failure you actually hit."

Running the CI recipe **locally before pushing**, the first `dbt build`
(bronze+silver) errored: the singular test comparing fact rows to source rows
references both a Bronze model and `fact_sales`, and dbt's default *eager*
indirect selection tried to run it before `fact_sales` existed. The fix was
`--indirect-selection cautious` on the intermediate build, so a test only runs
once all its inputs are built. It's a good example of why I run the pipeline
rather than trusting that the YAML "looks right" — the bug was invisible on
paper and obvious on execution.

## "What does the CI gate actually enforce?"

On every push/PR: `sqlfluff` lint (fails on any violation) → Python contract
tests → data generation → contract-validated Bronze load → full `dbt build`
(fails on any of the 195 tests) → source freshness. A red build blocks the merge.
Locally, a `pre-commit` config runs the same lint + tests before a commit, so
problems are caught even earlier.

## "Why Dagster over Airflow?"

Dagster is asset-centric: the things it schedules are the *data assets*
(tables/models), so lineage and freshness are first-class and the dbt models map
one-to-one to assets via dagster-dbt. Airflow is task-centric — you'd orchestrate
opaque scripts and rebuild the lineage story yourself. For a dbt-heavy platform,
dagster-dbt is the tighter, lower-glue fit.
