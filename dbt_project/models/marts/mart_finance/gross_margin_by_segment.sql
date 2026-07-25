-- gross_margin_by_segment: revenue, COGS, and gross margin % by customer segment
-- and fiscal year. Segment is taken POINT-IN-TIME from dim_customer (the segment
-- the customer was in when the sale happened), which is the payoff of the SCD2
-- customer join — margins are attributed to the segment as-was, not as-is.
-- Grain: one row per (fiscal_year, customer_segment).
-- Audience: value-creation review — which segments drive profitable growth.
{{ config(materialized='table') }}

with sales as (
    select
        fs.net_revenue,
        fs.cogs,
        fs.gross_profit,
        fs.customer_sk,
        dc.customer_id,
        dc.customer_segment,
        d.fiscal_year,
        d.fiscal_year_label
    from {{ ref('fact_sales') }} fs
    join {{ ref('dim_customer') }} dc on fs.customer_sk = dc.customer_sk
    join {{ ref('dim_date') }} d on fs.date_key = d.date_key
)

select
    fiscal_year,
    min(fiscal_year_label)                                            as fiscal_year_label,
    customer_segment,
    count(*)                                                          as order_lines,
    count(distinct customer_id)                                       as active_customers,
    sum(net_revenue)                                                  as net_revenue,
    sum(cogs)                                                         as cogs,
    sum(gross_profit)                                                 as gross_profit,
    round(100.0 * sum(gross_profit) / nullif(sum(net_revenue), 0), 2) as gross_margin_pct
from sales
group by fiscal_year, customer_segment
order by fiscal_year, customer_segment
