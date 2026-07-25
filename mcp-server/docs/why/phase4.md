# Why — Phase 4: `execute_sql` and `explain_query` behind the guards

Interview-defensible notes.

## "Why expose a raw-SQL tool at all? Isn't that the whole risk?"

Because a governed metric catalogue (Phase 5) can't answer *every* ad-hoc
question, and a CFO analyst will occasionally need one. The answer isn't to forbid
raw SQL — it's to make it **safe**: `execute_sql` runs every query through the
Phase 3 pipeline (single-statement, SELECT-only, blocklist, schema allowlist),
executes only the **wrapped, row-limited** form under a **timeout**, on a
**read-only** engine, and (Phase 6) **logs** every call with its verdict. The tool
description tells the model this is the escape hatch and to prefer `query_metric`.
It's a last resort, not a front door — but a *safe* last resort beats a forbidden
one that pushes people to copy data out to somewhere ungoverned.

## "What does the model get back — and why the `executed_sql` field?"

On success: the columns, the (capped) rows, `truncated`, and **the exact SQL that
ran** — the wrapped `SELECT * FROM (<your query>) AS _guarded LIMIT 1000`. Showing
the executed SQL is a trust/audit feature: there's no hidden rewriting the caller
can't see. On denial, the tool returns a clear reason (`"Denied by guard:
blocklisted keyword: DELETE"`), which doubles as a hint the LLM can act on —
qualify the table with `gold.`, or switch to a metric.

## "Why a separate `explain_query`, and how is it safe?"

`explain_query` returns the **query plan and estimated cardinalities without
running the query** — so an analyst (or the model) can sanity-check a heavy query
before paying for it. Two safety points:

1. It uses plain `EXPLAIN`, **never `EXPLAIN ANALYZE`** (which would execute).
2. It runs the **same guards first** (`assess`), so a malicious query is denied
   before it's ever planned — you can't use EXPLAIN as a side channel. E.g.
   `EXPLAIN SELECT * FROM read_csv(...)` is blocked by the blocklist before DuckDB
   could touch the file to infer its schema.

## "You wrap and re-limit even inside execute_sql — doesn't that change results?"

Only by capping row count, which is the intended guarantee. The wrap
(`SELECT * FROM (<q>) LIMIT 1000`) preserves the query's columns and semantics; it
just refuses to stream back more than the cap. For aggregates (the common CFO
case) the result is unchanged. If a genuine need for >1000 rows arises, that's a
deliberate config change (`max_rows`), logged and owned — not something an
arbitrary query can decide for itself.

## What this phase did NOT change

The guards. `execute_sql`/`explain_query` are thin tool wrappers over the Phase 3
`run_guarded`/`assess` — all 25 adversarial tests still pass unchanged, and the
new tool tests confirm the attacks are denied *through the MCP tool boundary*,
not just at the function level.
