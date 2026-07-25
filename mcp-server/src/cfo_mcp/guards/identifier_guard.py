"""Layer 3 — schema/identifier allowlist (semantic).

Parses the query into an AST (sqlglot, duckdb dialect) and verifies that EVERY
table reference resolves to an allowlisted `gold`/`marts` table that actually
exists. CTE names are exempt (they're local aliases, not real tables). A parse
failure is denied — if we can't understand it, we don't run it.

This is what a regex can't do reliably: know which tables a query touches, even
through joins, subqueries, and CTEs. It's why 'SELECT * FROM meta.column_docs'
is caught here even though it passed the syntactic guard.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from .decision import GuardDecision


def check_identifiers(query: str, allowed_schemas: tuple[str, ...], known_fqns) -> GuardDecision:
    stmt = query.strip().rstrip(";")
    try:
        tree = sqlglot.parse_one(stmt, dialect="duckdb")
    except Exception as exc:  # noqa: BLE001 — any parse error is a denial
        return GuardDecision(False, f"unparseable SQL: {exc}")
    if tree is None:
        return GuardDecision(False, "unparseable SQL")

    # Structural: the statement must be a read (SELECT / set-op / subquery), not
    # a command sqlglot recognised as something else.
    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)):
        return GuardDecision(False, f"only SELECT queries are allowed (got {type(tree).__name__})")

    allowed_lower = {s.lower() for s in allowed_schemas}
    known_lower = {f.lower() for f in known_fqns}
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}

    for table in tree.find_all(exp.Table):
        name = table.name
        schema = table.db  # schema part, '' if unqualified

        if not schema:
            if name.lower() in cte_names:
                continue  # local CTE reference
            matches = [f for f in known_lower if f.split(".")[1] == name.lower()]
            if len(matches) == 1:
                continue  # unambiguous bare table name in an allowlisted schema
            return GuardDecision(False, f"unqualified or unknown table '{name}'")

        if schema.lower() not in allowed_lower:
            return GuardDecision(
                False,
                f"table '{schema}.{name}' is outside the allowlisted schemas "
                f"{list(allowed_schemas)}",
            )
        if f"{schema}.{name}".lower() not in known_lower:
            return GuardDecision(False, f"unknown table '{schema}.{name}'")

    return GuardDecision(True, "identifiers ok")
