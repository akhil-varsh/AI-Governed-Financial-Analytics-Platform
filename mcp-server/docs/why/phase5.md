# Why — Phase 5: The semantic layer (the project's strongest point)

Interview-defensible notes.

## "What problem does the semantic layer actually solve?"

It stops the LLM from **inventing the wrong number**. Without it, "what was net
revenue?" makes the model write SQL — and it might sum `gross_revenue`, forget to
net out returns, double-count an SCD2 customer, or use the wrong fiscal calendar.
Each is a plausible, confident, *wrong* answer. With the semantic layer, the model
asks for the **metric** `net_revenue`, whose definition (`sum(net_revenue)`) is
authored once, owned by Finance, and reviewed. The number means the same thing
every time, no matter who asks or how they phrase it. That's the difference
between a demo and something a CFO would trust.

## "Why define metrics in YAML instead of Python?"

Because the people who *own* a metric definition are finance/analytics, not
engineers. YAML is reviewable in a pull request by a non-programmer, versioned,
and changed without a code deploy. The formula for gross margin lives in
`metrics.yaml`, next to its plain-English definition and its owner — a governance
artifact, not buried in code. (In production this is exactly what dbt's Semantic
Layer or Cube do; the YAML here is a faithful, dependency-light version of the
same idea.)

## "Walk me through why the compiler is safe."

Three separate guarantees:

1. **Keys are validated, not trusted.** The requested dimensions, filters, and
   time grain are checked against *this metric's* allowlist. `net_revenue` sliced
   by `cost_center` (a GL-only dimension) is denied with a reason — not silently
   ignored, not attempted.
2. **Values are parameterised, never concatenated.** Filter values become `?`
   placeholders bound at execution. The test proves it: a filter value of
   `"West'; DROP TABLE gold.fact_sales"` ends up **only in `params`**, never in
   the SQL string; it runs as a literal that matches no region, and the table is
   untouched.
3. **The formulas come from the reviewed YAML**, never the caller. The caller
   picks *which* metric and *how* to slice it — the compiler owns the SQL.

And then, belt-and-braces, the compiled SQL is still run through the Phase 3
guards (single-statement, SELECT-only, schema allowlist, `LIMIT`, timeout). A
governed path doesn't get to skip the guards.

## "The semantic layer also encodes correctness, not just safety — how?"

The hard parts of the star schema are baked into the definitions, so the LLM
can't get them wrong:

- **`customer_segment` is point-in-time.** It joins the SCD2 `dim_customer` on the
  fact's `customer_sk`, so a sale is attributed to the segment the customer was in
  *at the time* — the as-was margin, automatically.
- **`customer_count` uses the natural key.** `count(distinct customer_id)` (via a
  `required_joins` to `dim_customer`), not `count(distinct customer_sk)`, so a
  customer who changed segment isn't counted twice.
- **The fiscal calendar** (February start) comes from `dim_date`, so "by fiscal
  quarter" is correct without the model knowing the company's fiscal quirk.

An analyst writing raw SQL has to remember all three. Here they're encoded once.

## "Anything you'd flag as a judgement call?"

`customer_count` returns 15,001, not 15,000 — because 599 sales lines had a
missing customer id and roll up to the `UNKNOWN` member, which is a distinct
customer_id. That's honest (those sales exist and belong *somewhere*), and a
Finance owner can add a filter to exclude `UNKNOWN` if they'd rather. The point is
that the choice is visible and owned in the catalogue, not buried in ad-hoc SQL.

## Alternatives I rejected

| Choice | Rejected alternative | Why |
| --- | --- | --- |
| Metric catalogue | Let the LLM write SQL for numbers | It can invent a wrong definition, confidently; and it's a bigger injection surface |
| YAML definitions | Hardcode metrics in Python | Not reviewable by finance owners; needs a code deploy to change a formula |
| Lightweight in-repo compiler | dbt Semantic Layer / Cube | Right answer in production; overkill and heavy for a self-contained portfolio demo — but I can name it as the productionisation path |
| Parameterised filter values | Escape/quote them into the SQL | Escaping is a game you eventually lose; binding is safe by construction |
