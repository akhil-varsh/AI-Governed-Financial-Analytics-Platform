-- BUSINESS RULE: a non-return sales line can never have negative net revenue.
-- (Returns are legitimately negative and are excluded here.)
-- The test passes when this query returns zero rows.
select
    order_line_id,
    net_revenue
from {{ ref('fact_sales') }}
where not is_return
  and net_revenue < 0
