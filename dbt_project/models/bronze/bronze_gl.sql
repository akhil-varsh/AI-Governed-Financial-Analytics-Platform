-- Bronze: typed pass-through over the raw GL landing table.
with source as (
    select * from {{ source('raw', 'raw_gl_extract') }}
)

select
    gl_id,
    {{ try_cast('posting_date', 'date') }} as posting_date,
    account_code,
    account_name,
    region,
    cost_center,
    {{ try_cast('amount_usd', 'numeric') }} as amount_usd,
    currency,
    source_system,

    {{ try_cast('_loaded_at', 'timestamp') }} as _loaded_at,
    _source_file,
    _batch_id,
    _source_system
from source
