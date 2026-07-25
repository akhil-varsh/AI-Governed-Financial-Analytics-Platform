-- Bronze: typed pass-through over the raw POS landing table.
-- No dedup, no conforming, no business logic — that is Silver's job. This view
-- only casts the raw strings to their contracted types via the portability macro
-- so downstream models get real types without reaching into the raw layer.
with source as (
    select * from {{ source('raw', 'raw_pos_orders') }}
)

select
    order_line_id,
    order_id,
    {{ try_cast('order_date', 'date') }}          as order_date,
    customer_id,
    product_id,
    region,
    channel,
    {{ try_cast('quantity', 'int64') }}           as quantity,
    {{ try_cast('unit_price', 'numeric') }}       as unit_price,
    {{ try_cast('discount_pct', 'float64') }}     as discount_pct,
    {{ try_cast('gross_revenue', 'numeric') }}    as gross_revenue,
    {{ try_cast('discount_amount', 'numeric') }}  as discount_amount,
    {{ try_cast('net_revenue', 'numeric') }}      as net_revenue,
    currency,

    -- ingestion metadata (carried through unchanged)
    {{ try_cast('_loaded_at', 'timestamp') }}     as _loaded_at,
    _source_file,
    _batch_id,
    _source_system
from source
