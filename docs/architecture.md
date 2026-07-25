# Architecture

> This document grows with the build. Phase 1 establishes the skeleton and the
> data flow; later phases fill in each layer's models. The full mermaid diagram
> and end-to-end lineage land in Phase 8.

## Business problem

A PE sponsor owns **Northwind Retail Co**, a mid-market specialty retailer. The
sponsor's operating partner and Northwind's CFO need one trusted view of
**revenue, gross margin, and operating KPIs** by region, channel, product
category, and fiscal month to track value-creation between board meetings.

The data lives in three disconnected sources: the POS system, the ERP general
ledger, and a customer master (plus a product master and an FX feed). None of
them agree on keys, spelling, or currency. This platform reconciles them.

## Medallion layers

```
 Sources                 Bronze                Silver                 Gold                    Marts
 ┌──────────┐   land     ┌──────────┐  clean   ┌──────────┐  model    ┌──────────────┐  serve ┌───────────────┐
 │ POS      │──────────▶ │ raw +    │────────▶ │ typed,   │─────────▶ │ fact_sales   │──────▶ │ monthly_      │
 │ GL       │  append-   │ ingest   │ dedup,   │ conformed│  star     │ fact_gl      │  KPIs  │ revenue_bridge│
 │ customer │  only      │ metadata │ conform, │ business │  schema   │ dim_* (SCD2) │        │ gross_margin  │
 │ product  │            │ (_loaded │ null-    │ keys     │           │ dim_date     │        │ cohort_       │
 │ fx       │            │ _at …)   │ handle   │ resolved │           │ dim_region…  │        │ retention     │
 └──────────┘            └──────────┘          └──────────┘           └──────────────┘        └───────────────┘
```

| Layer      | Materialization | Contract                                                     |
| ---------- | --------------- | ------------------------------------------------------------ |
| **Bronze** | view            | Raw landed data, **append-only**, + `_loaded_at`, `_source_file`, `_batch_id`. No transformation. |
| **Silver** | table           | Cleaned, typed, **deduplicated**, conformed. One row per business entity per grain. Nulls handled explicitly. |
| **Gold**   | table           | Dimensional **star schema** for consumption. Facts + conformed dimensions, incl. SCD2. |
| **Marts**  | table           | Business-facing finance models. Read-only for stakeholders.  |

Each layer lands in its own BigQuery dataset (`<target>_bronze`, `_silver`,
`_gold`, `_marts`) via a custom `generate_schema_name` macro, so the warehouse
is browsable by layer and access can be granted to `marts` alone. See
[ADR-0002](decisions/0002-medallion-architecture.md).

## Gold star schema (target)

- **Facts:** `fact_sales` (grain: order line), `fact_gl` (grain: GL posting).
- **Dimensions:** `dim_customer` (SCD2 on segment + region), `dim_product`
  (SCD1 on description, SCD2 on category + list_price), `dim_date` (February
  fiscal year), `dim_region`, `dim_channel`.

## Stack & portability

BigQuery is the warehouse, but all SQL is ANSI-compliant and any vendor syntax
is isolated behind macros in `dbt_project/macros/warehouse_portability.sql`, so a
migration to Snowflake is a small, auditable change. See
[ADR-0003](decisions/0003-bigquery-portable-sql.md).

## Reliability guarantees (delivered across later phases)

- **Idempotency** — re-running any model or the whole pipeline twice yields
  identical results (incremental `merge` on the large fact table).
- **SCD2** — explicit `valid_from` / `valid_to` / `is_current`, via a dbt
  snapshot for one dimension and hand-written SQL for the other.
- **Data quality in three tiers** — source freshness/schema tests, model-level
  generic tests, and business-level singular tests.
- **Data contracts** — a YAML schema per feed + a Python validator that rejects
  a bad file *before* it reaches Bronze.
