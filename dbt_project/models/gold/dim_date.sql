-- dim_date: a generated calendar with Northwind's FEBRUARY fiscal year.
-- Grain: one row per calendar day. The fiscal columns are the whole point —
-- fiscal_year_start_month is a project var (=2), so the fiscal logic lives in one
-- place and every "by fiscal period" mart derives from here rather than
-- re-implementing month math. Vendor-specific date formatting is isolated in
-- macros (month_name/day_name/is_weekend) so this runs on BigQuery and DuckDB.
{{ config(materialized='table') }}

{% set fy_start = var('fiscal_year_start_month') %}

with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2021-02-01' as date)",
        end_date="cast('2026-02-01' as date)"
    ) }}
),

calendar as (
    select cast(date_day as date) as date_day
    from spine
),

parts as (
    select
        date_day,
        extract(year from date_day) as calendar_year,
        extract(quarter from date_day) as calendar_quarter,
        extract(month from date_day) as calendar_month,
        extract(day from date_day) as day_of_month,
        -- fiscal year: months before the fiscal start belong to the prior FY
        case
            when extract(month from date_day) >= {{ fy_start }}
                then extract(year from date_day)
            else extract(year from date_day) - 1
        end as fiscal_year,
        -- fiscal month: February = 1 … January = 12
        mod(extract(month from date_day) - {{ fy_start }} + 12, 12) + 1 as fiscal_month
    from calendar
)

select
    calendar_year * 10000 + calendar_month * 100 + day_of_month as date_key,
    date_day,
    calendar_year,
    calendar_quarter,
    calendar_month,
    {{ month_name('date_day') }} as month_name,
    day_of_month,
    {{ day_name('date_day') }} as day_name,
    {{ is_weekend('date_day') }} as is_weekend,
    fiscal_year,
    'FY' || {{ to_string('fiscal_year') }} as fiscal_year_label,
    fiscal_month,
    case
        when fiscal_month between 1 and 3 then 1
        when fiscal_month between 4 and 6 then 2
        when fiscal_month between 7 and 9 then 3
        else 4
    end as fiscal_quarter
from parts
