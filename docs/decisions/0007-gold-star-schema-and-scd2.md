# ADR-0007: Gold star schema, SCD2 approaches, and incremental strategy

- **Status:** Accepted
- **Date:** 2026-07-25

## Context

Gold must serve board-level reporting: revenue, margin, and KPIs by region,
channel, category, and fiscal month. It has to model slowly-changing dimensions
two different ways (per the brief) and guarantee idempotent fact builds.

## Decisions

### 1. Kimball star schema, not One Big Table
Two facts (`fact_sales` at order-line grain, `fact_gl` at posting grain) plus
conformed dimensions (`dim_date`, `dim_customer`, `dim_product`, `dim_region`,
`dim_channel`). Marts (Phase 5) can present wide/OBT-style models on top, but the
governed core is dimensional.

### 2. `dim_customer` — HAND-WRITTEN SCD2 (business-effective dates)
Built from the dated master extracts by detecting extracts where `customer_segment`
or `region` actually changes, and deriving `[valid_from, valid_to)` from those
change dates. **Why hand-written:** `fact_sales` must join the customer version
*in force on the order date* (point-in-time / "as-was"), which needs
business-effective validity windows. Verified: CUST-000001's pre-2023 order rolls
up as *Consumer*; its later orders as *SMB*.

### 3. `dim_product` — dbt SNAPSHOT (SCD2) + latest-description overlay (SCD1)
A dbt snapshot with the **check** strategy on `[category, list_price]` provides
the SCD2 history; the SCD1 `description` is overlaid with its latest value in the
`dim_product` model. **Why snapshot:** to use and be able to explain dbt's
built-in CDC, and to show combining snapshot-SCD2 with an SCD1 overlay — something
a single snapshot strategy can't express alone.

**Documented trade-off:** the check strategy dates versions by *capture time*
(`dbt_valid_from` = run time), not the business extract date. That's fine for
`dim_product`'s current-version ("as-is") join and for going-forward CDC, but it's
exactly why `dim_customer` — which needs point-in-time joins — is hand-written.
This contrast is the whole point of doing both.

### 4. Incremental `fact_sales` — MERGE (warehouse) on `order_line_id`
`fact_sales` is incremental. `unique_key = order_line_id` because it is the true
grain key: one physical row per order line, so upserting on it is exactly correct
and makes re-runs idempotent (verified: rebuild keeps 200,000 rows / 200,000
unique). The incremental predicate pulls only rows with a newer `_loaded_at`.

## Alternatives considered

| Decision | Rejected alternative | Why rejected |
| -------- | -------------------- | ------------ |
| Star schema | One Big Table as the core | Untestable joins, no conformed dims, poor governance; OBT lives in marts instead |
| Hand-written customer SCD2 | dbt snapshot for customer | Snapshot dates by capture time → can't do correct point-in-time fact joins |
| Snapshot for product | Hand-write product too | We're required to demonstrate a snapshot; product's simpler SCD2 fits it |
| MERGE on order_line_id | delete+insert on a date partition | order_line_id is a clean unique key; MERGE avoids the delete→insert gap and needs no reliable partition predicate |
| MERGE | full refresh every run | Not idempotent-by-merge, and wasteful on the large fact; full refresh is fine for the tiny fact_gl |

See also [ADR-0008](0008-dual-engine-duckdb-bigquery.md) for how MERGE (BigQuery)
vs delete+insert (DuckDB) is selected per engine.
