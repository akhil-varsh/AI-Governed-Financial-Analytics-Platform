-- BUSINESS RULE: every fact_sales foreign key must resolve to a dimension row
-- (no orphans). The relationships tests cover each FK individually; this is the
-- consolidated belt-and-braces check across all of them at once.
-- Passes when zero rows are returned.
select
    fs.order_line_id,
    fs.customer_sk,
    fs.product_sk,
    fs.region_sk,
    fs.channel_sk,
    fs.date_key
from {{ ref('fact_sales') }} fs
left join {{ ref('dim_customer') }} dc on fs.customer_sk = dc.customer_sk
left join {{ ref('dim_product') }}  dp on fs.product_sk  = dp.product_sk
left join {{ ref('dim_region') }}   dr on fs.region_sk   = dr.region_sk
left join {{ ref('dim_channel') }}  dch on fs.channel_sk = dch.channel_sk
left join {{ ref('dim_date') }}     dd on fs.date_key    = dd.date_key
where dc.customer_sk is null
   or dp.product_sk is null
   or dr.region_sk is null
   or dch.channel_sk is null
   or dd.date_key is null
