{#
    dbt SNAPSHOT — the built-in SCD2 mechanism (the counterpart to the
    hand-written dim_customer).

    Strategy 'check' on [category, list_price]: dbt inserts a new version only
    when one of those columns changes for a product_id, which is exactly SCD2 on
    those attributes. Description is deliberately NOT checked — it's SCD Type 1,
    overlaid with its latest value in dim_product.

    Building history from pre-existing dated extracts: the body selects each
    product's state AS OF a variable date, and we run `dbt snapshot` three times
    with product_snapshot_as_of set to each fiscal-year extract in order (see the
    `make snapshots` target). Each run detects the changes introduced by that
    extract and appends versions.

    Known trade-off (a teaching point, see ADR-0007): the check strategy dates
    validity by CAPTURE time (dbt_valid_from = run time), not the business
    extract date. That's fine for going-forward CDC and fine for dim_product's
    "as-is" join, but it's precisely why dim_customer — which needs
    business-effective, point-in-time joins — is hand-written instead.
#}
{% snapshot product_snapshot %}
{{
    config(
        target_schema='snapshots',
        unique_key='product_id',
        strategy='check',
        check_cols=['category', 'list_price']
    )
}}

with as_of as (
    select
        product_id,
        description,
        category,
        subcategory,
        list_price,
        standard_cost,
        extract_date,
        row_number() over (partition by product_id order by extract_date desc) as _rn
    from {{ ref('silver_products') }}
    where extract_date <= cast('{{ var("product_snapshot_as_of", "2024-02-01") }}' as date)
)

select
    product_id,
    description,
    category,
    subcategory,
    list_price,
    standard_cost,
    extract_date
from as_of
where _rn = 1

{% endsnapshot %}
