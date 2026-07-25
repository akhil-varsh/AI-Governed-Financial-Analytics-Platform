# Why — Phase 4: The Gold star schema and both SCD2 implementations

Interview-defensible notes for the dimensional layer.

## "You implemented SCD2 two ways. Why, and how do they differ?"

- **`dim_customer` is hand-written.** I detect the extracts where segment or
  region actually changes and derive `valid_from`/`valid_to` from those business
  dates. This gives **business-effective** history, which lets `fact_sales` do a
  **point-in-time** join — the customer's segment *as it was on the order date*.
  I proved it: CUST-000001's single pre-2023 order rolls up as **Consumer**, its
  nine later orders as **SMB**.
- **`dim_product` uses a dbt snapshot** (check strategy on category + list_price)
  with the latest `description` overlaid for SCD1. This demonstrates dbt's
  built-in CDC and how to mix SCD2 (snapshot) with SCD1 (overlay).

The key difference — and the reason I did both — is **dating**. A snapshot's
check strategy stamps validity at **capture time**, not the business date. That's
fine for product's "as-is" join and for going-forward change capture, but it
can't reconstruct business-effective history from pre-existing extracts. When I
needed correct point-in-time joins (customer), I hand-wrote it; when I wanted to
show the tool (product), I used the snapshot and documented the trade-off.

## "How did you build history into a snapshot from old extracts?"

Snapshots are designed to run repeatedly over time. To bootstrap history from the
three dated extracts, I run the snapshot three times, each pointing at the state
*as of* that extract (`make snapshots`). Each run's check strategy appends only
the versions where a tracked column changed. Result: 23 products with >1 version
(20 price changes + 3 category changes) — exactly the injected changes. In
production (Phase 7, Dagster), the snapshot runs on a schedule and accumulates
history going forward, so this replay is a one-time backfill.

## "Why is fact_sales incremental with merge, and why order_line_id as the key?"

`order_line_id` is the natural grain key — one physical row per order line — so
merging (upserting) on it is exactly right and makes the build idempotent:
re-running keeps 200,000 rows / 200,000 unique, never duplicating. The predicate
only reads rows with a newer `_loaded_at`, so daily runs are cheap. I chose
**merge over delete+insert** because a clean unique key makes merge the safer
upsert — no reliance on a partition predicate, no gap between a separate delete
and insert. (On the local DuckDB engine the same model uses delete+insert, which
DuckDB supports natively; both are idempotent on the same key — see ADR-0008.)

## "Why a star schema and not one big wide table?"

Governance and testability. The star has conformed dimensions I can test for
referential integrity (the `relationships` tests all pass — zero orphan FKs) and
reuse across many marts. A single wide table couples everything and can't be
tested the same way. I still serve wide, analyst-friendly models — but in the
**marts** layer, built on the governed star, not instead of it.

## "How do you know Gold is correct?"

Everything was built and tested on DuckDB: **88/88** Gold tests pass (unique,
not_null, accepted_values, and referential-integrity relationships). Beyond the
tests: the GL still ties to sales revenue within $0.12, gross margin is a
believable **37.8%**, both SCD2 histories match the injected changes exactly, the
point-in-time join resolves segments correctly, all 599 null-customer lines land
on the `UNKNOWN` member (no orphans), and a fact re-run is idempotent.

See [ADR-0007](../decisions/0007-gold-star-schema-and-scd2.md) and
[ADR-0008](../decisions/0008-dual-engine-duckdb-bigquery.md).
