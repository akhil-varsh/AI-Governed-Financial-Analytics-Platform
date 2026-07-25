"""Structured audit logging (Layer 5 of defense-in-depth).

Every tool call emits one structured JSON line with: timestamp, tool, arguments,
generated SQL, rows returned, latency, and the allow/deny decision + reason.

IMPORTANT — logs go to a FILE and to STDERR, never stdout. On an MCP *stdio*
server, stdout is the JSON-RPC protocol channel; writing logs there would corrupt
the transport and break the client. stderr is the correct diagnostic channel.

The `@audited` decorator wraps a tool: it records the arguments and latency, logs
`decision=deny` (with the reason) when the tool raises, and `decision=allow`
otherwise — pulling the generated SQL and row count off the result object when
present. Arguments are logged even on denial, so a blocked malicious query is
captured for forensics.
"""

from __future__ import annotations

import functools
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable

import structlog

_AUDIT_LOGGER_NAME = "cfo_mcp.audit"
_configured = False


def configure_audit(log_path: str | Path) -> None:
    global _configured
    if _configured:
        return
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # A DEDICATED, non-propagating logger — so only audit events reach the audit
    # log/stderr, and the MCP SDK's own logs don't pollute the JSON stream.
    audit_logger = logging.getLogger(_AUDIT_LOGGER_NAME)
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    audit_logger.handlers.clear()
    fmt = logging.Formatter("%(message)s")
    for handler in (logging.StreamHandler(sys.stderr), logging.FileHandler(log_path, encoding="utf-8")):
        handler.setFormatter(fmt)  # stderr, NOT stdout (MCP transport)
        audit_logger.addHandler(handler)

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(default=str),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_audit_logger():
    return structlog.get_logger(_AUDIT_LOGGER_NAME)


def _extract_sql(result: Any) -> str | None:
    for attr in ("executed_sql", "compiled_sql", "planned_sql"):
        value = getattr(result, attr, None)
        if value:
            return value
    return None


def _extract_rows(result: Any) -> int | None:
    for attr in ("row_count", "row_count_returned"):
        value = getattr(result, attr, None)
        if value is not None:
            return value
    if isinstance(result, list):
        return len(result)
    return None


def audited(tool_name: str) -> Callable:
    """Decorator: log every call to a tool with its decision and metadata."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            log = get_audit_logger()
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # denial or error — audit it, then re-raise
                log.info(
                    "tool_call",
                    tool=tool_name,
                    arguments=kwargs,
                    decision="deny",
                    reason=str(exc),
                    rows=0,
                    sql=None,
                    latency_ms=round((time.perf_counter() - start) * 1000, 2),
                )
                raise
            log.info(
                "tool_call",
                tool=tool_name,
                arguments=kwargs,
                decision="allow",
                reason="ok",
                rows=_extract_rows(result),
                sql=_extract_sql(result),
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            return result

        return wrapper

    return decorator
