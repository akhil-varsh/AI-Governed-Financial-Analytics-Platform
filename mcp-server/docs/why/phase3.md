# Why — Phase 3: The guards, adversarial-tests-first

Interview-defensible notes. This is the core of the project.

## The before/after

I wrote `tests/test_guards_adversarial.py` **first**, against a stub pipeline that
did no guarding, and ran it:

```
22 failed, 3 passed      # attacks succeed: out-of-schema reads return data,
                         # DuckDB escapes pass, SELECT * returns all 200,000 rows
```

Then I built `sql_guard` (Layer 2) and `identifier_guard` (Layer 3) until:

```
25 passed                # every attack denied with a specific reason;
                         # legit queries still allowed; 200k capped to 1000;
                         # runaway recursive query killed by the timeout
```

Each test asserts *why* it was denied (`"blocklisted keyword: DELETE"`,
`"table 'meta.column_docs' is outside the allowlisted schemas"`, …), not just that
it raised.

## Each layer: the attack it stops, and the gap if it were alone

| Layer | Stops | If it were the ONLY layer, this still gets through |
| --- | --- | --- |
| **1. Engine `read_only=True`** | Any write that reaches the engine (DROP/INSERT/UPDATE) fails. | Reads of *any* schema (`meta`, `information_schema`, `pg_catalog`); `COPY … TO 'file'` **writes to the filesystem** (read-only guards the DB, not the OS); `read_csv('/etc/passwd')` reads local files; unbounded 200k-row scans; runaway queries. |
| **2. `sql_guard` (syntactic)** | Stacked statements; anything not starting with SELECT/WITH; DDL/DML and DuckDB file functions (`read_csv`, `glob`, `COPY`, `ATTACH`, `INSTALL`, `LOAD`) via a whole-word blocklist; comment-obfuscation (comments stripped first); and it wraps every query with `LIMIT 1000`. | A perfectly valid `SELECT * FROM meta.column_docs` or `… information_schema.tables` — it's a single SELECT with no blocklisted word, so the syntactic guard passes it. Out-of-allowlist data leaks. |
| **3. `identifier_guard` (semantic)** | Reads of non-allowlisted schemas and unknown tables — by parsing to an AST and checking every table reference against the `gold`/`marts` allowlist (through joins, subqueries, CTEs). | On its own it parses only the first statement, so a stacked `; DROP` could still be executed; it doesn't enforce the row limit or timeout; and a bare table function like `read_csv(...)` isn't an AST *table* node, so it could slip — which is exactly why the blocklist (Layer 2) also exists. |
| **4. Protocol annotations** | Nothing by force — `readOnlyHint`/`destructiveHint` are a *declaration* a well-behaved client (Claude Desktop) uses to decide what it may call without a human confirm. | A malicious or buggy client that ignores hints. It's a signal, not a fence. |
| **5. Audit log** (Phase 6) | Nothing preventively — it records every allow/deny with the generated SQL. | Everything, in the moment; its value is detection and forensics after the fact. |

The point of defense-in-depth: **each layer has a hole another covers.** Layer 2
misses out-of-schema SELECTs; Layer 3 catches them. Layer 3 misses stacked
statements and file functions; Layer 2 catches them. Layer 1 is the backstop for
writes; Layers 2–3 stop them *before* execution (and would still protect a
Snowflake backend whose role grants were accidentally too broad).

## Why sqlglot for Layer 3 instead of more regex?

Because "which tables does this query touch?" is a parsing question, not a
pattern-matching one. A join to `meta.column_docs`, a subquery, or a CTE alias
that shadows a real name are all things a regex gets wrong. Parsing to an AST and
walking the `Table` nodes is correct and readable, and it structurally rejects
non-SELECT statements. A parse failure is itself a denial — if we can't understand
the query, we don't run it.

## Why the subquery wrap is itself a guard

Executing `SELECT * FROM (<q>) AS _guarded LIMIT 1000` means that even if some
non-SELECT slipped the prefix check, it can't run — only a SELECT is valid in that
position — and no query can return more than 1000 rows. It's a structural
backstop, not just cosmetics.

## The one thing I'm honest about

The `read_only` engine already blocks writes, so the blocklist's DROP/INSERT
entries are *defense in depth*, not the sole protection. They matter most for a
non-DuckDB backend (a Snowflake role) and as a clear, early, logged denial rather
than a deep engine error. I'd rather deny `DROP` at the door with a reason than
rely on the engine rejecting it three layers down.
