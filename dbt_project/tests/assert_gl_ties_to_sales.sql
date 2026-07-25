-- BUSINESS RULE (the finance tie-out): the GL revenue account (4000) must
-- reconcile to fact_sales net revenue. We assert equality within a $1.00
-- materiality tolerance, not exact-zero, because the GL was generated with
-- half-to-even rounding while the warehouse recomputes with half-away rounding
-- (~$0.12 on $173M — see docs/why/phase3.md). Passes when zero rows returned.
with sales as (
    select sum(net_revenue) as sales_net_usd from {{ ref('fact_sales') }}
),

gl_revenue as (
    select -sum(amount_usd) as gl_revenue_usd
    from {{ ref('fact_gl') }}
    where account_code = '4000'
)

select
    sales.sales_net_usd,
    gl_revenue.gl_revenue_usd,
    abs(sales.sales_net_usd - gl_revenue.gl_revenue_usd) as abs_diff
from sales, gl_revenue
where abs(sales.sales_net_usd - gl_revenue.gl_revenue_usd) > 1.00
