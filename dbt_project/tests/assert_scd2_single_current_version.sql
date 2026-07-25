-- BUSINESS RULE: each SCD2 entity has exactly ONE current version. Zero current
-- rows (broken close-out) or more than one (double-open) are both failures.
-- Passes when zero rows are returned.
select customer_id, count(*) as current_versions
from {{ ref('dim_customer') }}
where is_current
group by customer_id
having count(*) <> 1

union all

select product_id, count(*) as current_versions
from {{ ref('dim_product') }}
where is_current
group by product_id
having count(*) <> 1
