# ADR-0003: A semantic metric catalogue as the primary query path

- **Status:** Accepted

## Context

If the LLM answers "what was net revenue?" by writing SQL, it can confidently
produce a *wrong* number — summing gross instead of net, double-counting an SCD2
customer, or using the wrong fiscal calendar. For finance, a plausible wrong
number is worse than no answer.

## Decision

Define metrics in **`metrics.yaml`** (expression, base table, allowed
dimensions/filters, default time grain, plain-English definition, owner). The
`query_metric` tool compiles `metric + dimensions + filters + time_grain` into
safe parameterised SQL and is the **preferred** path; `execute_sql` is a guarded
last resort. Keys are validated against the catalogue; filter values are
parameter-bound; formulas come only from the YAML.

## Consequences

- The model asks for a **metric**, not a formula — it cannot invent a wrong
  definition. A number means the same thing everywhere.
- Definitions are owned/reviewed by finance in YAML, changeable without a code
  deploy.
- Correctness (point-in-time SCD2, distinct-customer by natural key, fiscal
  calendar) is encoded once, not left to the model.

## Alternatives

- **LLM writes SQL for numbers** — flexible but unsafe (wrong definitions; bigger
  injection surface). Kept as the guarded escape hatch, not the default.
- **dbt Semantic Layer / Cube** — the production answer; too heavy for a
  self-contained demo. This is a faithful, dependency-light version of the idea.
