-- dim_customer: SCD Type 2, HAND-WRITTEN (the counterpart to dim_product's dbt
-- snapshot). Tracks changes to customer_segment and region across the dated
-- master extracts.
--
-- WHY hand-written here: I want business-effective validity windows derived from
-- the extract dates (not the wall-clock time a snapshot happened to run), so
-- fact_sales can join "as-was" — the segment/region in force ON the order date.
-- A dbt snapshot dates history by capture time, which can't reconstruct
-- business-effective history from pre-existing extracts. See ADR-0007.
--
-- Method: detect the extracts where a tracked attribute actually CHANGES, treat
-- each as the start of a new version, and derive [valid_from, valid_to) from the
-- change dates. A synthetic 'UNKNOWN' member is unioned in so null-customer sales
-- lines have a home (no orphan FKs).
{{ config(materialized='table') }}

with src as (
    select
        customer_id,
        extract_date,
        customer_name,
        customer_segment,
        region,
        signup_date
    from {{ ref('silver_customers') }}
),

-- Compare each extract to the customer's previous extract.
flagged as (
    select
        src.*,
        lag(src.customer_segment) over w as prev_segment,
        lag(src.region) over w as prev_region
    from src
    window w as (partition by customer_id order by extract_date)
),

-- Keep only extracts that START a new version: the first one, or one where a
-- tracked attribute changed. Unchanged re-extracts are collapsed.
version_starts as (
    select
        *,
        (prev_segment is null) as is_first
    from flagged
    where
        prev_segment is null
        or customer_segment <> prev_segment
        or region <> prev_region
),

-- Derive validity windows: valid_to is the next version's start (half-open),
-- the open row runs to end-of-time, and the very first version opens at a far
-- past date so any early order still resolves to a version.
dated as (
    select
        customer_id,
        customer_name,
        customer_segment,
        region,
        signup_date,
        case when is_first then cast('1900-01-01' as date) else extract_date end as valid_from,
        coalesce(
            lead(extract_date) over (partition by customer_id order by extract_date),
            {{ scd_end_of_time() }}
        ) as valid_to
    from version_starts
),

with_unknown as (
    select
        customer_id,
        customer_name,
        customer_segment,
        region,
        signup_date,
        valid_from,
        valid_to
    from dated
    union all
    -- the sentinel member for unresolved customer ids
    select
        'UNKNOWN' as customer_id,
        'Unknown Customer' as customer_name,
        'Unknown' as customer_segment,
        'Unknown' as region,
        cast(null as date) as signup_date,
        cast('1900-01-01' as date) as valid_from,
        {{ scd_end_of_time() }} as valid_to
)

select
    {{ dbt_utils.generate_surrogate_key(['customer_id', 'valid_from']) }} as customer_sk,
    customer_id,
    customer_name,
    customer_segment,
    region,
    signup_date,
    valid_from,
    valid_to,
    (valid_to = {{ scd_end_of_time() }}) as is_current
from with_unknown
