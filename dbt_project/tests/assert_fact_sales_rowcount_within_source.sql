-- BUSINESS RULE: fact_sales row count must be within 10% of the distinct order
-- lines in the source. A larger gap means we silently dropped or duplicated
-- rows somewhere in Bronze -> Silver -> Gold. Passes when zero rows returned.
-- (In practice these are equal — dedup collapses the injected duplicates exactly
--  — but 10% is the guardrail that would fire on a real pipeline regression.)
with source_lines as (
    select count(distinct order_line_id) as n from {{ ref('bronze_pos_orders') }}
),

fact_lines as (
    select count(*) as n from {{ ref('fact_sales') }}
)

select
    source_lines.n as source_distinct_lines,
    fact_lines.n   as fact_rows
from source_lines, fact_lines
where abs(fact_lines.n - source_lines.n) > 0.10 * source_lines.n
