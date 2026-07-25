# Why — Phase 3: The Silver layer

Interview-defensible notes for the cleaning/conformance layer.

## "Walk me through what Silver actually does to a POS row."

Four things, each fixing an injected problem:

1. **Dedup** — exact duplicate lines (same `order_line_id`) collapse to one, via
   `row_number()` partitioned by the key, keeping rank 1. 204k → 200k.
2. **Conform region** — the raw label is trimmed and joined to a mapping seed
   that turns 20 spellings ("northeast", "N. East", "WEST"…) into 4 canonical
   regions. Anything unmapped becomes 'Unknown' and a test flags it.
3. **Resolve the key** — a null `customer_id` becomes the `'UNKNOWN'` sentinel,
   flagged with `is_unknown_customer`, so the line still counts toward revenue.
4. **Convert currency** — EUR monetary columns are converted to USD using the
   monthly FX lookup; the original-currency values are kept for audit.

Returns (negative quantity) are **kept and flagged**, never dropped, so revenue
nets correctly.

## "How do you know the cleaning is correct?"

Because it reconciles. After dedup + FX conversion, the sum of Silver
`net_revenue_usd` equals the GL revenue account (4000) to within **$0.12 on
$173.06M** (built and tested in BigQuery). If dedup double-counted, or FX were
wrong, or returns were dropped, that number would move by millions, not cents.

That $0.12 is itself a good talking point: it's a **rounding-convention
difference**, not an error. NumPy (which generated the GL) rounds half-to-even;
BigQuery's `ROUND()` rounds half-away-from-zero. Across ~24 half-cent lines that
nets to 12 cents — a relative error of 7×10⁻¹⁰. Real finance reconciliations
don't demand exact-zero; they use a materiality **tolerance**, which is exactly
what the Phase-6 business-level tie-out test asserts.

## "Why a seed table for region mapping instead of a regex or fuzzy match?"

Explicitness and safety. A seed is version-controlled, reviewable, and — crucially
— *testable*: a `relationships`/`accepted_values` test fails the build the moment
a new, unmapped spelling shows up, so a data drift becomes a loud CI failure
rather than a silent misclassification on the CFO's dashboard. A fuzzy matcher
would guess, non-deterministically, and could map "West" to the wrong region
without anyone noticing.

## "Why resolve null customers to UNKNOWN rather than dropping them?"

Those are real sales — dropping them would understate revenue and break the GL
tie-out. So they roll up to an explicit `UNKNOWN` customer, which Gold's
`dim_customer` will carry as a real member, giving the star schema zero orphan
foreign keys while keeping the money correct.

## "Why convert currency in Silver and not later?"

Currency conversion is a conformance concern — making the numbers comparable. If
I deferred it to Gold or the BI tool, every downstream consumer would reinvent it
and they'd drift. Conform once, in Silver, and keep the original currency for
audit.

## "Why not `QUALIFY` for the dedup? It's cleaner."

It is — but `QUALIFY` isn't ANSI SQL. ADR-0003 commits us to portable SQL so a
Snowflake migration stays cheap, so I use the portable `row_number()` + outer
`WHERE` form. Same result, no lock-in.

See [ADR-0006](../decisions/0006-silver-conformance-strategy.md).
