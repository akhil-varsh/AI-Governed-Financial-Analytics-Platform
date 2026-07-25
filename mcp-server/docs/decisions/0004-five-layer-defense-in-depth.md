# ADR-0004: Five-layer defense-in-depth for the raw-SQL path

- **Status:** Accepted

## Context

`execute_sql` accepts arbitrary query text from an untrusted LLM. No single check
is sufficient, and relying only on the read-only engine leaves real holes
(out-of-schema reads, `COPY TO`/`read_csv` touching the OS, unbounded scans).

## Decision

Five independent layers, each covering another's gap:

1. **Engine** — DuckDB `read_only=True` + statement timeout.
2. **SQL guard** — strip comments → single statement → `^(SELECT|WITH)` →
   whole-word blocklist (DDL/DML + DuckDB file functions) → wrap
   `SELECT * FROM (…) LIMIT 1000`.
3. **Identifier guard** — parse to a sqlglot AST; every table must be an
   allowlisted `gold`/`marts` table; non-SELECT structures denied.
4. **Protocol** — read-only tool annotations.
5. **Audit** — structured JSON record of every allow/deny with reason.

Built **adversarial-tests-first**: the attacks were written and watched succeed
against a stub, then the guards were built until all denied.

## Consequences

- Layer 2 misses out-of-schema SELECTs → Layer 3 catches them; Layer 3 misses
  stacked statements and file functions → Layer 2 catches them; Layer 1 backstops
  writes. Removing any one opens a hole (documented per-layer in
  `docs/why/phase3.md` and `docs/THREAT_MODEL.md`).
- Denials return a specific reason, which doubles as a self-correction hint for
  the model.

## Alternatives

- **Read-only engine only** — leaves the holes above.
- **Regex-only** for schema enforcement — can't reliably tell which tables a query
  touches; sqlglot parsing is correct. (See ADR — parsing beats pattern-matching.)
- **Allowlist of query shapes only** — too rigid; the metric compiler is the
  "only safe shapes" path, while the guards make free-form SELECT safe enough as a
  fallback.
