-- fact_gl: the general-ledger fact. Grain = one row per GL posting.
-- Small and fully refreshed each run (a table, not incremental) — the volume
-- doesn't justify incremental complexity. account_code/account_name/cost_center
-- are degenerate dimensions; region is a conformed FK.
{{ config(materialized='table') }}

with gl as (
    select * from {{ ref('silver_gl') }}
)

select
    g.gl_id,                                 -- degenerate dimension

    -- foreign keys
    (extract(year from g.posting_date) * 10000
        + extract(month from g.posting_date) * 100
        + extract(day from g.posting_date))   as date_key,
    g.posting_date,
    g.posting_month,
    dr.region_sk,

    -- degenerate GL attributes
    g.account_code,
    g.account_name,
    g.cost_center,

    -- measure
    g.amount_usd
from gl g
left join {{ ref('dim_region') }} dr
    on g.region = dr.region_name
