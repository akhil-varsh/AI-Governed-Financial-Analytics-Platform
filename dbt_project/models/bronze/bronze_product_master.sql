-- Bronze: typed pass-through over the raw product-master landing table.
with source as (
    select * from {{ source('raw', 'raw_product_master') }}
)

select
    {{ try_cast('extract_date', 'date') }} as extract_date,
    product_id,
    description,
    category,
    subcategory,
    {{ try_cast('list_price', 'numeric') }} as list_price,
    {{ try_cast('standard_cost', 'numeric') }} as standard_cost,

    {{ try_cast('_loaded_at', 'timestamp') }} as _loaded_at,
    _source_file,
    _batch_id,
    _source_system
from source
