"""Guard pipeline — composes the SQL guard (Layer 2) and identifier guard
(Layer 3), then runs the guarded query with a hard timeout + row limit.

Order matters: the cheap syntactic guard runs first (rejecting the obvious), then
the parse-based identifier guard. A query is executed only if BOTH pass, and only
in its wrapped, row-limited form.
"""

from __future__ import annotations

from ..adapters.base import WarehouseAdapter
from .decision import ExecutionOutcome, GuardDecision
from .identifier_guard import check_identifiers
from .sql_guard import check_sql


def assess(query: str, *, allowed_schemas: tuple[str, ...], known_fqns, max_rows: int) -> GuardDecision:
    syntactic = check_sql(query, max_rows)
    if not syntactic.allowed:
        return syntactic
    semantic = check_identifiers(query, allowed_schemas, known_fqns)
    if not semantic.allowed:
        return semantic
    return GuardDecision(allowed=True, reason="ok", safe_sql=syntactic.safe_sql)


def run_guarded(
    adapter: WarehouseAdapter,
    query: str,
    *,
    allowed_schemas: tuple[str, ...],
    known_fqns,
    max_rows: int,
    timeout_s: float,
    params: list | None = None,
) -> ExecutionOutcome:
    decision = assess(query, allowed_schemas=allowed_schemas, known_fqns=known_fqns, max_rows=max_rows)
    if not decision.allowed:
        return ExecutionOutcome(allowed=False, reason=decision.reason)
    try:
        result = adapter.execute(decision.safe_sql, timeout_s, params)
    except TimeoutError as exc:
        return ExecutionOutcome(allowed=False, reason=f"timeout: {exc}", executed_sql=decision.safe_sql)
    return ExecutionOutcome(allowed=True, reason="ok", result=result, executed_sql=decision.safe_sql)
