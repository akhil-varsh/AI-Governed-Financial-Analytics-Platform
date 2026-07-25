# ADR-0006: Silver cleaning & conformance strategy

- **Status:** Accepted
- **Date:** 2026-07-25

## Context

Silver must turn the deliberately dirty Bronze POS feed into a trustworthy,
one-row-per-grain sales table: deduplicated, region-conformed, business keys
resolved, and single-currency. Each of those four transforms has a real design
choice behind it.

## Decisions

### 1. Deduplication — `row_number()` + outer filter, not `QUALIFY`
Duplicates are exact copies sharing `order_line_id`. We rank with
`row_number() over (partition by order_line_id ...)` and keep rank 1 in an outer
`WHERE`. We deliberately avoid `QUALIFY` — although BigQuery/Snowflake/DuckDB all
support it, it is **not ANSI SQL**, and ADR-0003 commits us to portable SQL.

### 2. Region conformance — a seed mapping table, not regex/fuzzy logic
The 20 dirty spellings are mapped to 4 canonical regions via a version-controlled
seed (`seeds/region_conformance.csv`), joined on the trimmed raw value. A seed is
explicit, reviewable, and testable: a Phase-6 `relationships`/`accepted_values`
test fails the build the moment a **new** unmapped spelling appears, instead of a
fuzzy matcher silently guessing wrong.

### 3. Null business keys — resolve to an `UNKNOWN` member, don't drop
Missing `customer_id`s are resolved to a sentinel `'UNKNOWN'` and flagged with
`is_unknown_customer`. Dropping those lines would understate revenue (they still
represent real sales); quarantining them into a side table would break the
revenue tie-out. Gold's `dim_customer` carries a matching `UNKNOWN` member so the
star schema has no orphan foreign keys.

### 4. Currency conversion — done in Silver, keeping both currencies
EUR lines are converted to USD in Silver using the monthly `silver_fx_rates`
lookup, while the original-currency columns are retained for audit. Conversion is
a *cleaning/conformance* concern (making the data comparable), so it belongs in
Silver, not deferred to Gold or the BI tool where each consumer would reinvent it
inconsistently.

## Consequences

- Silver is portable, one-row-per-grain, single-currency, and reconciles: built
  in BigQuery, the converted `net_revenue_usd` ties to the GL revenue account to
  within **$0.12 on $173.06M** — a half-to-even (NumPy) vs half-away (BigQuery
  `ROUND`) rounding-convention difference, not an error. The Phase-6 business
  test asserts this with a materiality tolerance rather than exact-zero, which is
  how real reconciliations work.
- New dirty spellings surface as a test failure, not a silent misclassification.
- No revenue is lost to null keys, and Gold will have no orphan customers.

## Alternatives considered

| Decision | Rejected alternative | Why rejected |
| -------- | -------------------- | ------------ |
| `row_number()`+filter | `QUALIFY` | Not ANSI; breaks the portability commitment |
| Seed mapping | Regex/`CASE` normalization | Brittle for "N. East"/"W."; a matcher hides new bad values instead of failing |
| Seed mapping | Fuzzy string matching | Non-deterministic, unexplainable, can silently mis-map |
| Resolve null keys to `UNKNOWN` | Drop null-customer lines | Understates revenue; those are real sales |
| Resolve null keys to `UNKNOWN` | Quarantine to a reject table | Breaks the GL tie-out; adds reconciliation burden |
| Convert FX in Silver | Convert in Gold / BI | Each consumer would convert differently; conformance belongs in Silver |
