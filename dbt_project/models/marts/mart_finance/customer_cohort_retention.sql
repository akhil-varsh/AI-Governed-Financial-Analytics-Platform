-- customer_cohort_retention: acquisition-cohort retention. Customers are grouped
-- by the calendar month of their FIRST purchase (the cohort); for each month
-- since, we count how many of that cohort purchased again. This is the classic
-- retention triangle a PE sponsor uses to judge stickiness of the customer base.
-- Grain: one row per (cohort_month, period_number).
-- Unknown customers and pure returns are excluded (they aren't acquisitions).
{{ config(materialized='table') }}

with purchases as (
    select
        dc.customer_id,
        {{ date_trunc_month('fs.order_date') }} as order_month
    from {{ ref('fact_sales') }} as fs
    inner join {{ ref('dim_customer') }} as dc on fs.customer_sk = dc.customer_sk
    where
        not fs.is_unknown_customer
        and not fs.is_return
),

-- each customer's acquisition month
first_purchase as (
    select
        customer_id,
        min(order_month) as cohort_month
    from purchases
    group by customer_id
),

-- distinct active months per customer, tagged with their cohort
activity as (
    select distinct
        p.customer_id,
        fp.cohort_month,
        p.order_month
    from purchases as p
    inner join first_purchase as fp on p.customer_id = fp.customer_id
),

-- months elapsed since acquisition
periods as (
    select
        cohort_month,
        customer_id,
        (extract(year from order_month) - extract(year from cohort_month)) * 12
        + (extract(month from order_month) - extract(month from cohort_month)) as period_number
    from activity
),

cohort_size as (
    select
        cohort_month,
        count(distinct customer_id) as cohort_size
    from first_purchase
    group by cohort_month
),

active as (
    select
        cohort_month,
        period_number,
        count(distinct customer_id) as active_customers
    from periods
    group by cohort_month, period_number
)

select
    a.cohort_month,
    cs.cohort_size,
    a.period_number,
    a.active_customers,
    round(100.0 * a.active_customers / nullif(cs.cohort_size, 0), 2) as retention_pct
from active as a
inner join cohort_size as cs on a.cohort_month = cs.cohort_month
order by a.cohort_month, a.period_number
