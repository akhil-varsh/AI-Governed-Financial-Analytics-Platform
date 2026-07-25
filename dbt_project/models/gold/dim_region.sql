-- dim_region: small conformed region dimension. Sourced from the canonical
-- values in the conformance seed, plus an explicit 'Unknown' member so the
-- star schema never has an orphan region foreign key.
{{ config(materialized='table') }}

with regions as (
    select distinct region_canonical as region_name
    from {{ ref('region_conformance') }}
    union distinct
    select 'Unknown' as region_name
)

select
    {{ dbt_utils.generate_surrogate_key(['region_name']) }} as region_sk,
    region_name
from regions
