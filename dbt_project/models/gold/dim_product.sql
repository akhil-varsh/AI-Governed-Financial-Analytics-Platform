-- dim_product: SCD Type 1 on description, SCD Type 2 on category + list_price.
-- The SCD2 history comes from the dbt snapshot (product_snapshot); the SCD1
-- description is overlaid with its LATEST value from silver_products, so every
-- version row shows the current description while category/list_price retain
-- their historical values. This combination is why a snapshot alone isn't
-- enough — snapshots express one strategy, not a per-column mix.
{{ config(materialized='table') }}

with snap as (
    select * from {{ ref('product_snapshot') }}
),

-- SCD1 source: the most recent description per product.
latest_description as (
    select product_id, description
    from (
        select
            product_id,
            description,
            row_number() over (partition by product_id order by extract_date desc) as _rn
        from {{ ref('silver_products') }}
    ) ranked
    where _rn = 1
)

select
    {{ dbt_utils.generate_surrogate_key(['snap.product_id', 'snap.dbt_valid_from']) }} as product_sk,
    snap.product_id,
    ld.description,                        -- SCD1: always the latest description
    snap.category,                        -- SCD2
    snap.subcategory,
    snap.list_price,                      -- SCD2
    snap.standard_cost,
    snap.dbt_valid_from                                        as valid_from,
    coalesce(snap.dbt_valid_to, cast('9999-12-31' as timestamp)) as valid_to,
    (snap.dbt_valid_to is null)                               as is_current
from snap
left join latest_description ld
    on snap.product_id = ld.product_id
