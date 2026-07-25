# Why — Phase 2: Schema, preview, and the data-dictionary resource

Interview-defensible notes.

## "These tools take a table name from the model. How is that safe before the guard phase?"

By **resolution, not concatenation**. `get_schema` and `preview_table` never build
SQL from the raw argument. The adapter's `resolve_table(name)` looks the string up
in a dictionary of the allowlisted tables (built from `information_schema`), and
returns either a validated `TableInfo` — whose identifiers came from the engine,
not the user — or `None`. `None` becomes a **denial with a reason**. So
`"gold.fact_sales; DROP TABLE ..."` doesn't get sanitised; it simply fails to
resolve and is never executed. The query methods take a `TableInfo`, not a string,
so the type system enforces that only resolved tables reach SQL. Phase 3 extracts
this into a named `identifier_guard` with its own adversarial tests; the behaviour
is already correct here because I won't ship an injectable tool for even one phase.

## "Where do the column descriptions come from?"

Straight from the **lakehouse dbt manifest** at export time. The descriptions
already live in the dbt YAML (one source of truth); re-typing them here would let
them drift. `export_gold.py` reads `manifest.json`, extracts each model's column
descriptions, and stores them in a `meta` schema in the warehouse file. `get_schema`
and the data dictionary read from there. If the manifest is missing, descriptions
degrade gracefully to blank (or the hand-curated one-liners for tables).

## "Why is the `meta` schema not queryable?"

It holds descriptions, not business data, and it isn't in the allowlist
(`gold`, `marts`). So `list_tables` doesn't show it, `resolve_table` won't resolve
`meta.column_docs`, and the data dictionary excludes it (there's a test for that).
The adapter reads it directly for annotation only. Internal metadata should never
be reachable through a data tool.

## "Why a `schema://tables` resource as well as the `get_schema` tool?"

Different jobs. `get_schema` is a **tool** the model calls for one table on demand.
The resource is a **document** the model can read up front to understand the whole
warehouse — every table, column, type, and description in one markdown page. Giving
the LLM the full data dictionary as context is what stops it inventing column names
or misreading the grain, which is the most common way NL-to-SQL goes wrong.

## Attack → which layer stops it (so far)

| Attempt | Result | Why |
| --- | --- | --- |
| `get_schema("gold.secret_table")` | Denied | Not in the allowlisted set → no resolve |
| `get_schema("meta.column_docs")` | Denied | `meta` not allowlisted |
| `get_schema("gold.fact_sales; DROP ...")` | Denied | Doesn't resolve; raw string never hits SQL |
| `preview_table(n=9999)` | Rejected | Input schema constraint `n<=50`, and the adapter clamps too |

If resolution were the *only* guard, a cleverly-named real table could still be
previewed — which is fine here (every allowlisted table is meant to be readable).
The SQL-level guards in Phase 3/4 are what protect the raw-SQL escape hatch, where
arbitrary query text (not just a table name) is in play.
