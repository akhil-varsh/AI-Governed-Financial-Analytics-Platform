-- monthly_revenue_bridge: how net revenue is built each fiscal month, and how it
-- moves month-over-month. Two bridges in one model:
--   (a) COMPOSITION: gross sales − discounts + returns = net revenue
--   (b) PERIOD:      prior-month net + MoM delta = this-month net
-- Grain: one row per calendar month (carrying its fiscal-period labels).
-- Audience: the operating partner / CFO tracking the revenue trajectory.
{{ config(materialized='table') }}

with sales as (
    select
        fs.gross_revenue,
        fs.discount_amount,
        fs.net_revenue,
        fs.cogs,
        fs.gross_profit,
        fs.is_return,
        {{ date_trunc_month('fs.order_date') }} as month_start,
        d.fiscal_year,
        d.fiscal_month,
        d.fiscal_year_label
    from {{ ref('fact_sales') }} fs
    join {{ ref('dim_date') }} d on fs.date_key = d.date_key
),

monthly as (
    select
        month_start,
        fiscal_year,
        fiscal_month,
        min(fiscal_year_label) as fiscal_year_label,

        -- (a) composition of net revenue. sales_net + returns = net_revenue is
        -- EXACT (same net column split by return flag). gross_sales and discounts
        -- are the informational gross->net detail; because each line's USD gross,
        -- discount and net are independently rounded to cents, gross_sales −
        -- discounts only approximates sales_net (off by rounding cents), so the
        -- exact identity we assert is the return/non-return split, not gross−disc.
        sum(case when not is_return then gross_revenue else 0 end)   as gross_sales,
        sum(case when not is_return then discount_amount else 0 end) as discounts,
        sum(case when not is_return then net_revenue else 0 end)     as sales_net,
        sum(case when is_return then net_revenue else 0 end)         as returns,
        sum(net_revenue)                                             as net_revenue,

        -- profitability
        sum(cogs)                                                    as cogs,
        sum(gross_profit)                                            as gross_profit,
        count(*)                                                     as order_lines
    from sales
    group by month_start, fiscal_year, fiscal_month
)

select
    month_start,
    fiscal_year,
    fiscal_year_label,
    fiscal_month,

    -- (a) informational gross->net detail, plus the exact split:
    --     sales_net + returns = net_revenue
    gross_sales,
    discounts,
    sales_net,
    returns,
    net_revenue,

    -- (b) period-over-period bridge
    lag(net_revenue) over (order by month_start)                      as prior_net_revenue,
    net_revenue - lag(net_revenue) over (order by month_start)        as mom_change,
    round(
        100.0 * (net_revenue - lag(net_revenue) over (order by month_start))
        / nullif(lag(net_revenue) over (order by month_start), 0), 2
    )                                                                 as mom_change_pct,

    -- profitability
    cogs,
    gross_profit,
    round(100.0 * gross_profit / nullif(net_revenue, 0), 2)           as gross_margin_pct,
    order_lines
from monthly
order by month_start
