# ADR-0003: BigQuery warehouse with warehouse-portable SQL

- **Status:** Accepted
- **Date:** 2026-07-24

## Context

We need a cloud warehouse that a final-year student can run for free, that a PE
consulting firm would plausibly use, and that does not lock us in — the firm's
next portfolio company might standardise on Snowflake.

## Decision

Use **BigQuery (sandbox tier)** as the warehouse: no billing account required,
generous free quota, first-class dbt adapter. To avoid lock-in:

1. Keep all model SQL **ANSI-compliant**.
2. Isolate every vendor-specific function (e.g. `SAFE_CAST`, `CURRENT_TIMESTAMP()`,
   `GENERATE_UUID`) behind macros in
   `dbt_project/macros/warehouse_portability.sql`. Models call the macro, never
   the vendor function directly.
3. Use `dbt_utils` cross-database macros for surrogate keys and common tests.

A migration to Snowflake then becomes: swap the dbt adapter + profile, and edit
one macros file — an auditable diff, not a project-wide rewrite.

## Consequences

- Free, reproducible warehouse for a portfolio project.
- A single, reviewable seam for portability; the discipline is enforced by
  convention and code review (and is greppable — searching models for
  backticks or `SAFE_` should return nothing).
- Slight indirection: engineers must learn to reach for the macro. Accepted.

## Alternatives considered

- **DuckDB (local, embedded)** — tempting for zero-setup reproducibility and it
  would make CI trivial. Rejected as the *primary* warehouse because the target
  role is cloud-warehouse-centric and the brief specifies BigQuery; a local
  DuckDB target is a reasonable future addition for offline unit-testing of SQL.
  *(Trade-off flagged as required by the brief.)*
- **Snowflake** — the likely enterprise target, but no free-forever sandbox for
  a student; we instead make the *migration path* cheap rather than starting
  there.
- **Postgres** — cheap and portable but not a columnar analytics warehouse;
  wrong shape for the workload and not representative of the role.
