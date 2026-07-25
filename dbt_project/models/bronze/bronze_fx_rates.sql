-- Bronze: typed pass-through over the raw FX-rates landing table.
with source as (
    select * from {{ source('raw', 'raw_fx_rates') }}
)

select
    {{ try_cast('rate_date', 'date') }}       as rate_date,
    from_currency,
    to_currency,
    {{ try_cast('rate', 'numeric') }}         as rate,

    {{ try_cast('_loaded_at', 'timestamp') }} as _loaded_at,
    _source_file,
    _batch_id,
    _source_system
from source
