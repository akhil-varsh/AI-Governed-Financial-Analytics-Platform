-- Silver: conformed general-ledger postings.
-- The GL is clean at source, so cleaning is light: enforce the grain and drop
-- any accidental double-load. Region/account are already conformed upstream.
-- Grain: one row per gl_id.
with bronze as (
    select * from {{ ref('bronze_gl') }}
),

ranked as (
    select
        gl_id,
        posting_date,
        {{ date_trunc_month('posting_date') }} as posting_month,
        account_code,
        account_name,
        region,
        cost_center,
        amount_usd,
        currency,
        source_system,
        _loaded_at,
        _source_file,
        _batch_id,
        row_number() over (
            partition by gl_id
            order by _loaded_at desc, _batch_id desc
        ) as _rn
    from bronze
)

select
    gl_id,
    posting_date,
    posting_month,
    account_code,
    account_name,
    region,
    cost_center,
    amount_usd,
    currency,
    source_system,
    _loaded_at,
    _source_file,
    _batch_id
from ranked
where _rn = 1
