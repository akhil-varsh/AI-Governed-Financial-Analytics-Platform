-- BUSINESS RULE: gross margin % must be a sane figure in [-100, 100] everywhere
-- it is reported. A value outside that band signals a COGS/revenue data error.
-- Passes when zero rows are returned.
select 'gross_margin_by_segment' as model, {{ to_string('fiscal_year') }} as grp, gross_margin_pct
from {{ ref('gross_margin_by_segment') }}
where gross_margin_pct not between -100 and 100

union all

select 'monthly_revenue_bridge' as model, {{ to_string('month_start') }} as grp, gross_margin_pct
from {{ ref('monthly_revenue_bridge') }}
where gross_margin_pct not between -100 and 100
