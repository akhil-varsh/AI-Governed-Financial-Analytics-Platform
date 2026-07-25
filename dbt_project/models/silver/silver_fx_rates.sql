-- Silver: conformed FX rates keyed by month + currency pair.
-- Grain: one row per (rate_month, from_currency, to_currency). Idempotent — if a
-- batch were loaded twice, we keep a single row per key (latest ingestion wins).
with bronze as (
    select * from {{ ref('bronze_fx_rates') }}
),

ranked as (
    select
        {{ date_trunc_month('rate_date') }} as rate_month,
        from_currency,
        to_currency,
        rate,
        row_number() over (
            partition by {{ date_trunc_month('rate_date') }}, from_currency, to_currency
            order by _loaded_at desc, _batch_id desc
        ) as _rn
    from bronze
)

select
    rate_month,
    from_currency,
    to_currency,
    rate
from ranked
where _rn = 1
