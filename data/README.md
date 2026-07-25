# Northwind source feeds (synthetic)

Everything here is produced by [`scripts/generate_synthetic_data.py`](../scripts/generate_synthetic_data.py),
seeded (`SEED = 42`) so `make data` is byte-for-byte reproducible. The generated
`*.csv` files are **git-ignored** — the generator is the source of truth, not the
data. This mirrors how a real consulting engagement keeps the *pipeline* in
version control, not the client's extracts.

## Feeds

| File                          | Stands in for      | Grain                     | Rows    |
| ----------------------------- | ------------------ | ------------------------- | ------- |
| `pos_orders.csv`              | POS system         | one order **line**        | ~204k   |
| `gl_extract.csv`              | ERP general ledger | one GL **posting**        | ~1.3k   |
| `customer_master_YYYYMMDD.csv`| Customer master    | one customer per extract  | 15k × 3 |
| `product_master_YYYYMMDD.csv` | Product master     | one product per extract   | 800 × 3 |
| `fx_rates.csv`                | Treasury / FX feed | one rate per month/pair   | 72      |

The customer and product masters are delivered as **three dated full extracts**
(FY2022 / FY2023 / FY2024 fiscal-year starts). Periodic full dumps are how most
mid-market source systems actually hand over master data, and they give the SCD2
logic real historical versions to reconstruct.

## Why the GL ties out

The GL revenue account (`4000 Sales Revenue`) and COGS account (`5000`) are
posted **from** the aggregated USD sales facts, at month × region × channel
grain. That guarantees a business-level reconciliation:

> `SUM(fact_gl.amount_usd WHERE account_code = '4000')` (sign-flipped)
> **==** `SUM(fact_sales.net_revenue_usd)`

At last generation this was **~$173.06M**. Real finance data reconciles;
a business-level dbt test (Phase 6) asserts this holds within a rounding
tolerance. OpEx accounts (`6000` payroll, `6100` rent, `6200` marketing) are
un-tied plugs added only so the ledger reads like a real trial balance.

## Deliberately injected data-quality problems

These exist so the Silver layer has real work to do and the tests have real
upstream failures to catch. Each is deterministic under the seed.

| # | Problem                                   | Where           | Silver's job                          |
| - | ----------------------------------------- | --------------- | ------------------------------------- |
| A | ~2% exact **duplicate** order lines       | `pos_orders`    | dedup on `order_line_id`              |
| B | ~8% inconsistent **region spellings** (20 variants) | `pos_orders` | conform to `dim_region`      |
| C | ~0.3% **null `customer_id`**              | `pos_orders`    | quarantine / flag "unknown customer"  |
| D | ~3% **negative quantities** (returns)     | `pos_orders`    | keep — must net correctly, not drop   |
| E | two **currencies** (USD + EUR)            | `pos_orders`    | convert to USD via `fx_rates`         |
| F | **3 customers** change segment/region     | customer master | `dim_customer` SCD **Type 2**         |
| G | products change `list_price` / `category` | product master  | `dim_product` SCD **Type 2**          |

### The three SCD2 customers (issue F)

| customer_id  | change                                    | effective extract |
| ------------ | ----------------------------------------- | ----------------- |
| `CUST-000001`| segment `Consumer` → `SMB`                | FY2023 (2023-02-01) |
| `CUST-000002`| segment `Mid-Market` → `Enterprise`       | FY2024 (2024-02-01) |
| `CUST-000003`| segment `SMB` → `Mid-Market`, region `Southeast` → `West` | FY2023 (2023-02-01) |

### Product changes (issue G)

- `PROD-0001`–`PROD-0020`: `list_price` +8% at the FY2024 extract (SCD2).
- `PROD-0050`–`PROD-0052`: `category` → `Outdoor` at the FY2023 extract (SCD2).
- `PROD-0100`–`PROD-0105`: `description` corrected at FY2024 (SCD **Type 1** —
  overwrite, no history).

## Regenerating

```bash
make data        # or: uv run python scripts/generate_synthetic_data.py
```
