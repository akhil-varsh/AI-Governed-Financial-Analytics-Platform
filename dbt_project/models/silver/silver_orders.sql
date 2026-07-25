-- Silver: cleaned, conformed sales order lines. This is where the four injected
-- data problems in the POS feed are resolved:
--   1. DEDUP        — exact duplicate lines collapsed to one per order_line_id.
--   2. CONFORM      — 20 dirty region spellings mapped to 4 canonical regions.
--   3. RESOLVE KEY  — null customer_id resolved to the 'UNKNOWN' member.
--   4. CONVERT FX   — EUR monetary columns converted to USD via monthly rates.
-- Returns (negative quantity) are KEPT and flagged, not dropped, so revenue nets
-- correctly. Grain: one row per order_line_id (unique after dedup).
with bronze as (
    select * from {{ ref('bronze_pos_orders') }}
),

region_map as (
    select
        raw_region,
        region_canonical
    from {{ ref('region_conformance') }}
),

fx as (
    select
        rate_month,
        from_currency,
        rate
    from {{ ref('silver_fx_rates') }}
),

-- 1. DEDUP: rank exact copies (which share order_line_id and all metadata) and
--    keep one. row_number()+outer filter is used instead of QUALIFY to stay
--    ANSI-portable (QUALIFY is not standard SQL).
deduped as (
    select
        b.*,
        row_number() over (
            partition by b.order_line_id
            order by b._loaded_at, b._batch_id
        ) as _dedup_rn
    from bronze as b
)

select
    d.order_line_id,
    d.order_id,
    d.order_date,
    {{ date_trunc_month('d.order_date') }} as order_month,

    -- 3. RESOLVE null customer_id -> sentinel; flag it for transparency.
    coalesce(nullif(trim(d.customer_id), ''), 'UNKNOWN') as customer_id,
    (d.customer_id is null or trim(d.customer_id) = '') as is_unknown_customer,

    d.product_id,

    -- 2. CONFORM region; anything the mapping doesn't cover becomes 'Unknown'
    --    (a relationships test in Phase 6 guards against new, unmapped spellings).
    coalesce(rm.region_canonical, 'Unknown') as region,
    d.region as region_raw,

    d.channel,
    d.quantity,
    (d.quantity < 0) as is_return,
    d.currency,

    -- monetary columns in the ORIGINAL line currency (kept for auditability)
    d.unit_price,
    d.discount_pct,
    d.gross_revenue,
    d.discount_amount,
    d.net_revenue,

    -- 4. CONVERT to USD reporting currency (USD rows have rate 1).
    coalesce(fx.rate, 1) as fx_rate_to_usd,
    round(d.gross_revenue * coalesce(fx.rate, 1), 2) as gross_revenue_usd,
    round(d.discount_amount * coalesce(fx.rate, 1), 2) as discount_amount_usd,
    round(d.net_revenue * coalesce(fx.rate, 1), 2) as net_revenue_usd,

    d._loaded_at,
    d._source_file,
    d._batch_id
from deduped as d
left join region_map as rm
    on trim(d.region) = rm.raw_region
left join fx
    on
        fx.rate_month = {{ date_trunc_month('d.order_date') }}
        and d.currency = fx.from_currency
where d._dedup_rn = 1
