# Data dictionary

The consumption layer (Gold star schema + finance marts) in full, plus a summary
of the upstream layers. Every column here also carries a description in the dbt
docs site ([`docs/dbt_docs/`](dbt_docs/)) — this page is the human-readable
reference; the docs site is the browsable, lineage-linked one.

All monetary measures are **USD** (the reporting currency; EUR converted in
Silver).

---

## Gold — facts

### `fact_sales` — grain: one order line

| Column | Type | Description |
| --- | --- | --- |
| `order_line_id` | string | Order-line natural key; unique (merge key). |
| `order_id` | string | Parent order (degenerate dimension). |
| `date_key` | int | FK → `dim_date` (order date, YYYYMMDD). |
| `order_date` | date | Order date (convenience). |
| `customer_sk` | string | FK → `dim_customer`, **point-in-time** version. |
| `product_sk` | string | FK → `dim_product`, current version. |
| `region_sk` | string | FK → `dim_region`. |
| `channel_sk` | string | FK → `dim_channel`. |
| `is_return` | bool | Line is a return (negative quantity). |
| `is_unknown_customer` | bool | Source customer id was missing. |
| `currency` | string | Original line currency (USD/EUR). |
| `fx_rate_to_usd` | numeric | Rate applied to convert to USD. |
| `quantity` | int | Units (negative on returns). |
| `gross_revenue` | numeric | Gross revenue, USD. |
| `discount_amount` | numeric | Discount, USD. |
| `net_revenue` | numeric | Net revenue (gross − discount), USD. |
| `cogs` | numeric | Cost of goods sold (quantity × standard_cost), USD. |
| `gross_profit` | numeric | net_revenue − cogs, USD. |
| `_loaded_at` | timestamp | Ingestion watermark (incremental). |

### `fact_gl` — grain: one GL posting

| Column | Type | Description |
| --- | --- | --- |
| `gl_id` | string | GL posting natural key (degenerate). |
| `date_key` | int | FK → `dim_date` (posting date). |
| `posting_date` | date | Posting date. |
| `posting_month` | date | First day of the posting month. |
| `region_sk` | string | FK → `dim_region`. |
| `account_code` | string | GL account (4000 revenue, 5000 COGS, 6xxx opex). |
| `account_name` | string | Account name. |
| `cost_center` | string | Cost center / channel. |
| `amount_usd` | numeric | Posting amount, USD (revenue negative, expense positive). |

---

## Gold — dimensions

### `dim_customer` — SCD Type 2 (grain: one version per customer)

| Column | Type | Description |
| --- | --- | --- |
| `customer_sk` | string | Surrogate key (customer_id + valid_from); unique per version. |
| `customer_id` | string | Natural key (repeats across versions). |
| `customer_name` | string | Display name. |
| `customer_segment` | string | Segment in force during the version (Consumer/SMB/Mid-Market/Enterprise/Unknown). |
| `region` | string | Home region in force during the version. |
| `signup_date` | date | Onboarding date (null for UNKNOWN member). |
| `valid_from` | date | Inclusive start of validity (business-effective). |
| `valid_to` | date | Exclusive end (9999-12-31 for current). |
| `is_current` | bool | True for the active version. |

### `dim_product` — SCD1 on description, SCD2 on category/list_price

| Column | Type | Description |
| --- | --- | --- |
| `product_sk` | string | Surrogate key (product_id + snapshot valid_from). |
| `product_id` | string | Natural key (repeats across versions). |
| `description` | string | Latest description (SCD1 — overwritten). |
| `category` | string | Category in force during the version (SCD2). |
| `subcategory` | string | Subcategory. |
| `list_price` | numeric | List price in force during the version (SCD2). |
| `standard_cost` | numeric | Standard unit cost, USD. |
| `valid_from` | timestamp | Version start (snapshot capture time). |
| `valid_to` | timestamp | Version end (9999-12-31 for current). |
| `is_current` | bool | True for the active version. |

### `dim_date` — February fiscal year (grain: one day)

| Column | Type | Description |
| --- | --- | --- |
| `date_key` | int | YYYYMMDD surrogate key. |
| `date_day` | date | Calendar date. |
| `calendar_year` / `calendar_quarter` / `calendar_month` | int | Calendar parts. |
| `month_name` / `day_name` | string | Full names. |
| `day_of_month` | int | 1–31. |
| `is_weekend` | bool | Saturday/Sunday. |
| `fiscal_year` | int | Fiscal year (Feb start; Feb 2023–Jan 2024 = 2023). |
| `fiscal_year_label` | string | e.g. `FY2023`. |
| `fiscal_month` | int | February = 1 … January = 12. |
| `fiscal_quarter` | int | 1–4, derived from fiscal_month. |

### `dim_region` / `dim_channel` — small conformed dimensions

| Column | Type | Description |
| --- | --- | --- |
| `region_sk` / `channel_sk` | string | Surrogate key. |
| `region_name` / `channel_name` | string | Canonical name (region includes `Unknown`). |

---

## marts (`mart_finance`)

### `monthly_revenue_bridge` — grain: one calendar month

Composition bridge (`sales_net + returns = net_revenue`, exact) and period bridge
(`prior_net_revenue + mom_change = net_revenue`), plus margin. Key columns:
`month_start`, `fiscal_year`, `fiscal_month`, `gross_sales`, `discounts`,
`sales_net`, `returns`, `net_revenue`, `prior_net_revenue`, `mom_change`,
`mom_change_pct`, `cogs`, `gross_profit`, `gross_margin_pct`, `order_lines`.

### `gross_margin_by_segment` — grain: (fiscal_year, customer_segment)

Segment is **point-in-time** from SCD2 `dim_customer`. Columns: `fiscal_year`,
`fiscal_year_label`, `customer_segment`, `order_lines`, `active_customers`,
`net_revenue`, `cogs`, `gross_profit`, `gross_margin_pct`.

### `customer_cohort_retention` — grain: (cohort_month, period_number)

Acquisition-cohort retention triangle. Columns: `cohort_month`, `cohort_size`,
`period_number` (months since acquisition), `active_customers`, `retention_pct`.

---

## Upstream layers (summary)

- **Sources (`raw`)** — five landed tables (`raw_pos_orders`, `raw_gl_extract`,
  `raw_customer_master`, `raw_product_master`, `raw_fx_rates`); every source
  column stored as string + ingestion metadata. Governed by the YAML contracts in
  [`ingestion/contracts/`](../ingestion/contracts/).
- **Bronze (`bronze_*`)** — typed 1:1 views over the raw tables (no business
  logic).
- **Silver (`silver_*`)** — `silver_orders` (deduped, region-conformed,
  key-resolved, FX-converted), `silver_customers` / `silver_products` (versioned
  history for SCD2), `silver_gl`, `silver_fx_rates`.

Full column-level detail for every model is in the browsable dbt docs site,
[`docs/dbt_docs/index.html`](dbt_docs/).
