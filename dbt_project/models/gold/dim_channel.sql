-- dim_channel: small conformed channel dimension, derived from the distinct
-- channels observed in the cleaned sales feed.
{{ config(materialized='table') }}

with channels as (
    select distinct channel as channel_name
    from {{ ref('silver_orders') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['channel_name']) }} as channel_sk,
    channel_name
from channels
