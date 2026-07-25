# Threat model

The premise: an LLM (Claude Desktop / Cursor) is given tools that reach a finance
data warehouse, and the person driving it — or a prompt-injection payload in some
document the LLM read — may be adversarial. The job of this server is to make that
safe. This document lists what an attacker could try and which layer stops it.

## Assets

- The finance data (sales + GL of a PE portfolio company).
- The warehouse's integrity (no writes/DDL).
- The host filesystem and network (no exfiltration / SSRF).
- The correctness of reported numbers (no fabricated definitions).

## Trust boundaries

- The **LLM and its inputs are untrusted.** Prompts, and any document content the
  LLM ingests, can attempt injection.
- The **tool arguments are untrusted** — every string could be hostile.
- The **metric YAML, the guard code, and the warehouse schema are trusted** (they
  are reviewed and version-controlled).

## The five layers

| # | Layer | Mechanism |
| - | ----- | --------- |
| 1 | Engine | DuckDB opened `read_only=True` (a Snowflake backend would be a SELECT-only role on one schema). |
| 2 | SQL guard | Comment-strip → single statement → `^(SELECT\|WITH)` → whole-word blocklist → wrap `SELECT * FROM (…) LIMIT 1000`. |
| 3 | Identifier guard | Parse to AST (sqlglot); every table must be an allowlisted `gold`/`marts` table; CTE names exempt; non-SELECT denied. |
| 4 | Protocol | Tool annotations `readOnlyHint/destructiveHint/idempotentHint/openWorldHint`. |
| 5 | Audit | One structured JSON line per call (args, SQL, rows, latency, allow/deny + reason) to file + stderr. |

## Attack → defense matrix

| Attack | Example | Stopped by | Result |
| ------ | ------- | ---------- | ------ |
| Destroy data | `DROP TABLE gold.fact_sales` | L2 prefix + blocklist; L1 backstop | Denied: "must start with SELECT" |
| Write data | `UPDATE …`, `INSERT …`, `MERGE …` | L2 blocklist; L1 backstop | Denied: "blocklisted keyword" |
| Stacked statement | `SELECT 1; DROP TABLE …` | L2 single-statement | Denied: "only a single statement" |
| Comment obfuscation | `SELECT 1 /* */; DR/**/OP …` | L2 comment-strip → single-statement | Denied |
| CTE hiding a write | `WITH x AS (SELECT 1) DELETE …` | L2 blocklist | Denied: "blocklisted keyword: DELETE" |
| Read outside allowlist | `SELECT * FROM meta.column_docs` / `information_schema.tables` | L3 schema allowlist | Denied: "outside allowlisted schemas" |
| Unknown table | `SELECT * FROM gold.secret` | L3 existence check | Denied: "unknown table" |
| Local-file read (path traversal) | `SELECT * FROM read_csv('/etc/passwd')` | L2 blocklist (read_csv/read_parquet/glob) | Denied: "blocklisted keyword: READ_CSV" |
| Exfiltration to disk | `COPY (…) TO 'C:/leak.csv'` | L2 prefix + blocklist | Denied |
| Load extension / attach db | `INSTALL httpfs` / `ATTACH 'x'` | L2 prefix + blocklist | Denied |
| Table-name injection (tool arg) | `get_schema("gold.f; DROP …")` | Identifier resolution (Phase 2) | Denied: doesn't resolve |
| Filter-value injection (metric) | `filters={region: "W'; DROP …"}` | Parameter binding | Inert literal; 0 rows; no write |
| Prompt-injected wrong definition | "net revenue = gross" | Semantic layer | Formula fixed in YAML; LLM can't change it |
| Unicode prefix trick | `\u200bSELECT 1` | L2 ASCII-only prefix regex | Denied: "must start with SELECT" |
| Resource exhaustion (rows) | `SELECT * FROM fact_sales` (200k) | L2 `LIMIT 1000` wrap | Capped at 1000 |
| Resource exhaustion (time) | recursive CTE spin | Statement timeout (interrupt) | Denied: "timeout" |

Every row above has a test in `tests/test_guards_adversarial.py`,
`tests/test_tools.py`, or `tests/test_metrics.py`.

## Why defense-in-depth (no single layer is enough)

- **L1 alone** blocks writes but not out-of-schema reads, `COPY TO`/`read_csv`
  (which touch the OS, not the DB), unbounded scans, or runaway queries.
- **L2 alone** misses a perfectly valid `SELECT` against `meta`/`information_schema`.
- **L3 alone** parses only the first statement (so a stacked `; DROP` could slip),
  doesn't cap rows or time, and can miss a table *function* like `read_csv`.
- **L4** is advisory — a misbehaving client can ignore it.
- **L5** prevents nothing; it makes everything accountable.

Each layer covers another's gap; see `docs/why/phase3.md` for the detailed
gap analysis.

## Residual risks / out of scope (honest limitations)

- **Read access to all of `gold`/`marts` is intentional** — anyone who can use
  the server can read any governed table. Row-/column-level security (e.g. a deal
  team seeing only their portfolio company) is a real next step, not implemented
  here.
- **No authn/z or rate limiting at the MCP layer** — trust is delegated to
  whoever launched the server (Claude Desktop on the user's machine). A hosted,
  multi-tenant deployment would need identity, per-user allowlists, and quotas.
- **The blocklist is a denylist** for DuckDB verbs/functions; a brand-new dangerous
  function in a future DuckDB version wouldn't be covered until added. L1
  (read-only) and L3 (schema allowlist) are the allowlist-style backstops that
  don't depend on enumerating every bad verb.
- **The metric SQL is trusted** — a mistake in `metrics.yaml` would produce a
  wrong (but safe) number. That's why metrics are reviewed and owned.
