# Northwind Retail Co — PE Value-Creation Lakehouse

A medallion-architecture data platform that gives a private-equity sponsor's
operating partner and Northwind Retail Co's CFO a **single trusted view of
revenue, gross margin, and operating KPIs** by region, channel, product
category, and fiscal month — so value-creation progress is visible between
board meetings.

Today the underlying data is scattered across disconnected CSV extracts from the
POS system, the ERP general ledger, and a customer master. This project lands,
cleans, conforms, and models that data into a governed star schema and a set of
finance marts.

> **Status:** built in phases. This README grows with the project; the full
> architecture diagram, data dictionary, and ADR index land in the final phase.

---

## Stack

| Concern         | Choice                                   |
| --------------- | ---------------------------------------- |
| Warehouse       | BigQuery (sandbox tier), ANSI-portable SQL |
| Transformation  | dbt Core                                 |
| Orchestration   | Dagster (local, `dagster-dbt`)           |
| Ingestion       | Python 3.11 + pandas                     |
| CI              | GitHub Actions (sqlfluff → `dbt build`)  |
| Packaging       | `uv` with a pinned lockfile              |

## Architecture (medallion)

```
 Source CSVs ──▶ Bronze ──▶ Silver ──▶ Gold (star schema) ──▶ mart_finance
 (POS, GL,       raw +      cleaned,     facts + dims           board-ready
  masters)       metadata   conformed    (incl. SCD2)           KPIs
```

- **Bronze** — raw landed data, append-only, plus ingestion metadata
  (`_loaded_at`, `_source_file`, `_batch_id`). No transformation.
- **Silver** — cleaned, typed, deduplicated, conformed; one row per business
  entity per grain; nulls handled explicitly.
- **Gold** — dimensional star schema (`fact_sales`, `fact_gl`, `dim_customer`
  SCD2, `dim_product` SCD1+SCD2, `dim_date` with a February fiscal year,
  `dim_region`, `dim_channel`).
- **mart_finance** — `monthly_revenue_bridge`, `gross_margin_by_segment`,
  `customer_cohort_retention`.

## Quickstart

```bash
# 1. Environment (installs Python 3.11, all deps, and dbt packages)
make setup

# 2. Generate the reproducible synthetic dataset into data/raw/
make data

# 3. Configure the warehouse connection
cp .env.example .env          # then edit with your GCP project + keyfile
#   export the vars into your shell (see .env.example header for a PowerShell one-liner)

# 4. Verify the connection
make connection-test          # runs `dbt debug`

# 5. Build + test everything
make build
```

Run `make help` to see every target.

## Repository layout

```
northwind-lakehouse/
  docs/            architecture, data dictionary, ADRs, per-phase "why" notes
  ingestion/       data contracts (YAML), validator, Bronze loader
  dbt_project/     models (bronze/silver/gold/marts), snapshots, tests, macros
  orchestration/   Dagster assets + schedule
  scripts/         synthetic data generator
  .github/         CI workflow
```

## Data

The dataset is **synthetic and reproducible** (`scripts/generate_synthetic_data.py`,
seeded). It covers three fiscal years, ~200k order lines, ~15k customers, ~800
products, 4 regions, and 3 channels, plus a GL extract that **ties out** to
sales net revenue. It also carries deliberately injected data-quality problems
for the Silver layer to resolve. See [`data/README.md`](data/README.md).

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — layer-by-layer design
- [`docs/decisions/`](docs/decisions/) — Architecture Decision Records
- [`docs/why/`](docs/why/) — per-phase "why" notes, written to be defended in an
  interview
- [`docs/AI_WORKFLOW.md`](docs/AI_WORKFLOW.md) — how this was built with AI assistance
