"""Layer 2 — application-level SQL guard (syntactic).

Fast, deterministic checks on the raw query text, in order:
  1. strip SQL comments (so nothing hides inside `/* */` or `--`)
  2. exactly one statement (no stacked statements)
  3. must start with SELECT or WITH (ASCII-whitespace prefix only)
  4. no blocklisted keyword as a whole word (DDL/DML + DuckDB file functions)
  5. wrap the query as `SELECT * FROM (<q>) LIMIT <max_rows>` for execution

This is a syntactic net. It does NOT understand which tables a query touches —
that is Layer 3's job (identifier_guard). The two together are defense in depth:
either alone leaves a gap, both together are hard to slip past.
"""

from __future__ import annotations

import re

from .decision import GuardDecision

# Whole-word blocklist. The brief's DDL/DML set, plus the DuckDB data-source
# functions that would allow local-file reads/writes (read_csv, glob, …) and a
# few admin verbs. Deliberately excludes REPLACE/SET-as-substrings that collide
# with legitimate expressions (e.g. the string function replace()).
_BLOCKLIST = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "MERGE", "COPY",
    "GRANT", "REVOKE", "ATTACH", "DETACH", "INSTALL", "LOAD", "PRAGMA",
    "EXPORT", "IMPORT", "VACUUM", "REINDEX",
    # DuckDB local-file / data-source functions (path traversal / exfiltration)
    "READ_CSV", "READ_CSV_AUTO", "READ_PARQUET", "READ_JSON", "READ_JSON_AUTO",
    "READ_TEXT", "READ_BLOB", "PARQUET_SCAN", "CSV_SCAN", "GLOB",
]

_BLOCK_RE = re.compile(r"(?i)\b(" + "|".join(_BLOCKLIST) + r")\b")
_PREFIX_RE = re.compile(r"(?is)^[ \t\r\n\f\v]*(select|with)\b")  # ASCII whitespace only
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"--[^\n]*")


def _strip_comments(sql: str) -> str:
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    return sql


def _statements(sql: str) -> list[str]:
    # Safe to split on ';' now that comments (which could hide one) are gone.
    return [s for s in (part.strip() for part in sql.split(";")) if s]


def check_sql(query: str, max_rows: int) -> GuardDecision:
    if not query or not query.strip():
        return GuardDecision(False, "empty query")

    normalized = _strip_comments(query).strip()
    if not normalized:
        return GuardDecision(False, "query is only comments")

    statements = _statements(normalized)
    if len(statements) != 1:
        return GuardDecision(
            False, f"only a single statement is allowed (found {len(statements)} statements)"
        )
    stmt = statements[0]

    if not _PREFIX_RE.match(stmt):
        return GuardDecision(False, "query must start with SELECT or WITH")

    hit = _BLOCK_RE.search(stmt)
    if hit:
        return GuardDecision(False, f"blocklisted keyword: {hit.group(1).upper()}")

    safe_sql = f"SELECT * FROM (\n{stmt}\n) AS _guarded LIMIT {int(max_rows)}"
    return GuardDecision(True, "sql ok", safe_sql=safe_sql)
