-- fact_sales: the revenue fact. Grain = one row per order line.
--
-- IDEMPOTENCY / INCREMENTAL: materialized incremental, keyed on
-- unique_key = order_line_id (the natural grain key). On BigQuery the strategy is
-- MERGE (a clean upsert on that key — the production choice); on the local DuckDB
-- engine it's delete+insert (DuckDB doesn't need BigQuery's MERGE, and both are
-- idempotent on the same unique key). Either way, re-building updates rows in
-- place instead of duplicating them, so building twice yields identical results.
-- The incremental predicate only pulls rows loaded since the last build
-- (_loaded_at watermark), so steady-state runs are cheap. We prefer MERGE over
-- plain delete+insert on the warehouse because order_line_id is a reliable unique
-- key and MERGE avoids the gap between a separate delete and insert. See ADR-0007.
--
-- FK linkage: dim_customer is joined POINT-IN-TIME (segment/region as-was on the
-- order date) — the payoff of business-effective SCD2. dim_product is joined on
-- its CURRENT version (as-is), because the product snapshot dates by capture
-- time, not business date.
{{
    config(
        materialized='incremental',
        unique_key='order_line_id',
        incremental_strategy=('merge' if target.type == 'bigquery' else 'delete+insert'),
        on_schema_change='append_new_columns'
    )
}}

with orders as (
    select * from {{ ref('silver_orders') }}
    {% if is_incremental() %}
    where _loaded_at > (select coalesce(max(_loaded_at), cast('1900-01-01' as timestamp)) from {{ this }})
    {% endif %}
),

product_current as (
    select product_id, product_sk, standard_cost
    from {{ ref('dim_product') }}
    where is_current
)

select
    o.order_line_id,                         -- degenerate dimension + merge key
    o.order_id,                              -- degenerate dimension

    -- foreign keys
    (extract(year from o.order_date) * 10000
        + extract(month from o.order_date) * 100
        + extract(day from o.order_date))                       as date_key,
    o.order_date,
    dc.customer_sk,
    pc.product_sk,
    dr.region_sk,
    dch.channel_sk,

    -- flags carried for convenience / filtering
    o.is_return,
    o.is_unknown_customer,
    o.currency,
    o.fx_rate_to_usd,

    -- measures (USD reporting currency)
    o.quantity,
    o.gross_revenue_usd                                          as gross_revenue,
    o.discount_amount_usd                                        as discount_amount,
    o.net_revenue_usd                                            as net_revenue,
    round(o.quantity * pc.standard_cost, 2)                      as cogs,
    round(o.net_revenue_usd - (o.quantity * pc.standard_cost), 2) as gross_profit,

    o._loaded_at
from orders o
left join {{ ref('dim_customer') }} dc
    on o.customer_id = dc.customer_id
   and o.order_date >= dc.valid_from
   and o.order_date <  dc.valid_to
left join product_current pc
    on o.product_id = pc.product_id
left join {{ ref('dim_region') }} dr
    on o.region = dr.region_name
left join {{ ref('dim_channel') }} dch
    on o.channel = dch.channel_name
