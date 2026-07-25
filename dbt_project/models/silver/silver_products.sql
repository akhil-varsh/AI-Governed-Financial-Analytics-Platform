-- Silver: conformed product-master history.
-- KEEP every dated extract (one row per product per extract_date) so Gold's
-- dim_product can build SCD1 (description) and SCD2 (category, list_price).
-- Grain: one row per (product_id, extract_date).
with bronze as (
    select * from {{ ref('bronze_product_master') }}
),

ranked as (
    select
        product_id,
        extract_date,
        trim(description)  as description,
        category,
        subcategory,
        list_price,
        standard_cost,
        _loaded_at,
        _source_file,
        _batch_id,
        row_number() over (
            partition by product_id, extract_date
            order by _loaded_at desc, _batch_id desc
        ) as _rn
    from bronze
)

select
    product_id,
    extract_date,
    description,
    category,
    subcategory,
    list_price,
    standard_cost,
    _loaded_at,
    _source_file,
    _batch_id
from ranked
where _rn = 1
