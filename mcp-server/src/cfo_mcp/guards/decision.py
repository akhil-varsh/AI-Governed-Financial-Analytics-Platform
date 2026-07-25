"""Shared result types for the guard layer."""

from __future__ import annotations

from dataclasses import dataclass

from ..adapters.base import QueryResult


@dataclass(frozen=True)
class GuardDecision:
    """Verdict of static analysis on a query."""

    allowed: bool
    reason: str
    safe_sql: str | None = None  # the wrapped, execution-safe SQL when allowed


@dataclass(frozen=True)
class ExecutionOutcome:
    """Verdict + result of a guarded execution."""

    allowed: bool
    reason: str
    result: QueryResult | None = None
    executed_sql: str | None = None  # the wrapped SQL actually run (transparency/audit)
