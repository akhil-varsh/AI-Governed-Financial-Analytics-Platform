-- BUSINESS RULE: a customer's SCD2 validity windows must never overlap — at any
-- point in time exactly one version is in force. Two half-open intervals
-- [a_from, a_to) and [b_from, b_to) overlap iff a_from < b_to and b_from < a_to.
-- Passes when zero rows are returned.
select
    a.customer_id,
    a.valid_from as a_valid_from,
    a.valid_to   as a_valid_to,
    b.valid_from as b_valid_from,
    b.valid_to   as b_valid_to
from {{ ref('dim_customer') }} a
join {{ ref('dim_customer') }} b
    on a.customer_id = b.customer_id
   and a.customer_sk <> b.customer_sk
   and a.valid_from < b.valid_to
   and b.valid_from < a.valid_to
