# Why — Phase 6: Three-tier testing and documentation

Interview-defensible notes for data quality and docs.

## "Describe your testing strategy."

Three tiers, each catching a different class of problem:

1. **Source (tier 1)** — `dbt source freshness` + schema tests on the raw feeds
   (not_null / unique / accepted_values on keys and domains). This catches a bad
   or stale *file* at the front door, before it can propagate. All 5 sources pass
   freshness; the schema tests guard the raw contract in the warehouse (mirroring
   the Python contract gate at ingestion).
2. **Model (tier 2)** — generic tests on every model: `unique`, `not_null`,
   `relationships`, `accepted_values`. This is the bulk of the suite and enforces
   grain, referential integrity (zero orphan FKs), and value domains.
3. **Business (tier 3)** — 7 hand-written **singular** tests that encode rules a
   generic test can't express (below).

Total: **195 tests, all passing** — far past the 25-test bar. The point isn't the
count; it's that each layer has the right *kind* of test.

## "What are the singular business tests, and why singular?"

Generic tests check structure; singular tests check *business truth*:

- **assert_gl_ties_to_sales** — GL revenue (account 4000) reconciles to
  fact_sales net revenue within a **$1.00 materiality tolerance** (actual: $0.12).
  Tolerance, not exact-zero, because the GL uses half-to-even rounding and the
  warehouse recomputes half-away — the professional way to reconcile.
- **assert_no_overlapping_scd2_windows** — a customer's SCD2 validity windows
  never overlap (exactly one version in force at any time).
- **assert_scd2_single_current_version** — each SCD2 entity has exactly one
  current row (no double-open, no lost close-out).
- **assert_net_revenue_sign** — only returns may be negative.
- **assert_gross_margin_pct_in_range** — margin ∈ [-100, 100] everywhere reported.
- **assert_fact_sales_rowcount_within_source** — fact volume within 10% of source
  distinct lines (a regression guardrail against silent drop/duplication).
- **assert_no_orphan_fact_foreign_keys** — consolidated orphan check across all
  fact FKs.

## "The GL tie-out test uses a tolerance — isn't that cheating?"

No — it's how finance reconciles. Demanding exact-zero across independently
rounded values would make the test flap on immaterial cents. A **materiality
tolerance** ($1 on $173M) asserts the number that matters — the books agree —
while ignoring rounding noise. A test that fails on $0.12 is a test people learn
to ignore; a test with a sensible tolerance is one they trust.

## "You claim no blank descriptions — did you verify that?"

Yes, programmatically. After `dbt docs generate`, a script cross-checks the
**catalog** (columns actually in the warehouse) against the **manifest**
(documented columns) and reports any model/source/column with an empty
description. Result: **0 blank** across 20 models, 5 sources, and every catalog
column. The docs site (`docs/dbt_docs/`) is a committed static snapshot with full
lineage from raw sources through to the finance marts.

## "Why commit generated docs?"

So a reviewer (or interviewer) can open `docs/dbt_docs/index.html` and see the
whole lineage, catalog, and tests without standing up the warehouse. It's a
deliverable, regenerated with `make docs-static`.
