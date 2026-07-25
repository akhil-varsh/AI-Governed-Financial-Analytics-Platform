-- Silver: conformed customer-master history.
-- We KEEP every dated extract (one row per customer per extract_date) because
-- Gold's dim_customer needs the version history to build SCD Type 2. Cleaning
-- here is: trim text, guarantee the grain is unique, and drop any accidental
-- double-load (append-only Bronze could contain the same extract twice).
-- Grain: one row per (customer_id, extract_date).
with bronze as (
    select * from {{ ref('bronze_customer_master') }}
),

ranked as (
    select
        customer_id,
        extract_date,
        trim(customer_name) as customer_name,
        customer_segment,
        region,
        signup_date,
        _loaded_at,
        _source_file,
        _batch_id,
        row_number() over (
            partition by customer_id, extract_date
            order by _loaded_at desc, _batch_id desc
        ) as _rn
    from bronze
)

select
    customer_id,
    extract_date,
    customer_name,
    customer_segment,
    region,
    signup_date,
    _loaded_at,
    _source_file,
    _batch_id
from ranked
where _rn = 1
