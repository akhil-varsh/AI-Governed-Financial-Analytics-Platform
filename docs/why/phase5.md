# Why — Phase 5: Finance marts

Interview-defensible notes for the business-facing layer.

## "What are these marts and who reads them?"

Three board-ready models on top of the Gold star, for the PE operating partner
and the CFO:

- **monthly_revenue_bridge** — how net revenue is composed each month and how it
  moves month-over-month. The value-creation trajectory at a glance (net revenue
  grows ~$3.7M → ~$6.0M/month across the three years).
- **gross_margin_by_segment** — revenue, COGS and gross margin % by customer
  segment and fiscal year. Which segments drive profitable growth.
- **customer_cohort_retention** — acquisition-cohort retention triangle. How
  sticky the customer base is — a core PE diligence lens.

## "Why marts on top of the star, instead of querying the star directly?"

Marts encode the *business definitions* once — what "net revenue", "gross margin
%", "a cohort", "retention" mean — so every consumer (BI dashboard, board deck,
ad-hoc query) uses the same numbers. This is where a governed star pays off: the
marts are thin, readable, and testable because the hard work (conforming,
SCD2, FX, grain) already happened underneath. It's also where wide,
analyst-friendly ("OBT-style") shapes belong — built *on* the star, not instead
of it (see ADR-0002).

## "The revenue bridge — why two different reconciliations?"

A revenue bridge should tie out exactly. There are two identities:

1. **Return/non-return split** (`sales_net + returns = net_revenue`) — this is
   **exact**, because it's the same `net_revenue` column split by a flag. That's
   the identity I *test*.
2. **Gross → net** (`gross_sales − discounts ≈ sales_net`) — informational only,
   because each line's USD gross, discount, and net are **independently rounded**
   to cents, so summing them can differ from the rounded net by a few cents per
   month.

I hit exactly this: my first test asserted `gross − discounts + returns =
net_revenue` and it failed on 34 of 36 months — by cents. Rather than paper over
it, I test the identity that's exact by construction and keep gross/discounts as
informational detail. Knowing *which* identities survive rounding, and testing
those, is the point.

## "Segment margin — as-is or as-was?"

**As-was.** `gross_margin_by_segment` joins `fact_sales` to the SCD2
`dim_customer` on the surrogate key, so each sale is attributed to the segment
the customer was in **when the sale happened**. A customer upgraded from SMB to
Enterprise mid-year contributes to SMB for their early orders and Enterprise
later — which is what you want for a value-creation review. This is the direct
payoff of the point-in-time SCD2 work in Phase 4.

## "How is the cohort retention built?"

Customers are grouped by the calendar month of their **first purchase** (the
cohort). For each subsequent month, I count how many of that cohort purchased
again, as a share of the cohort size. Period 0 is always 100%. Unknown customers
and pure returns are excluded — a return isn't an acquisition, and you can't
cohort an unknown. The result is the familiar retention triangle
(cohort_month × months-since-acquisition).
