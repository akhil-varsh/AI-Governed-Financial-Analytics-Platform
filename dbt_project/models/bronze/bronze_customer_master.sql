-- Bronze: typed pass-through over the raw customer-master landing table.
-- All dated extracts land in one table; the extract_date discriminates versions.
with source as (
    select * from {{ source('raw', 'raw_customer_master') }}
)

select
    {{ try_cast('extract_date', 'date') }} as extract_date,
    customer_id,
    customer_name,
    customer_segment,
    region,
    {{ try_cast('signup_date', 'date') }} as signup_date,

    {{ try_cast('_loaded_at', 'timestamp') }} as _loaded_at,
    _source_file,
    _batch_id,
    _source_system
from source
