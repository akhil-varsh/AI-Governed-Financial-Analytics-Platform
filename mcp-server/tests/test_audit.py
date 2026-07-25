"""Phase 6 — the audit layer.

Verifies that every tool call emits one structured JSON line with the required
fields, that a denial is logged with its reason (and the offending arguments),
and that the log is pure JSON (no protocol noise leaks into it).
"""

from __future__ import annotations

import json
import logging

import pytest

from cfo_mcp import audit
from cfo_mcp.config import settings


@pytest.fixture()
def audit_log(tmp_path, monkeypatch):
    # Point the audit logger at a temp file for this test.
    monkeypatch.setattr(audit, "_configured", False)
    path = tmp_path / "audit.log"
    audit.configure_audit(path)
    yield path
    # Restore: close temp handlers and reconfigure to the real audit log.
    logger = logging.getLogger(audit._AUDIT_LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    audit._configured = False
    audit.configure_audit(settings.audit_log_path)


def _read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_allow_is_logged_with_sql_and_rows(audit_log):
    class Result:
        executed_sql = "SELECT * FROM (select 1) LIMIT 1000"
        row_count = 42

    @audit.audited("execute_sql")
    def tool(query: str):
        return Result()

    tool(query="select 1")
    (record,) = _read(audit_log)
    assert record["tool"] == "execute_sql"
    assert record["decision"] == "allow"
    assert record["rows"] == 42
    assert record["sql"].startswith("SELECT * FROM")
    assert record["arguments"] == {"query": "select 1"}
    assert set(record) >= {"tool", "arguments", "decision", "reason", "rows", "sql", "latency_ms", "timestamp"}


def test_denial_is_logged_with_reason_and_arguments(audit_log):
    @audit.audited("query_metric")
    def tool(metric: str):
        raise ValueError("Denied: unknown metric 'revenue_lol'")

    with pytest.raises(ValueError):
        tool(metric="revenue_lol")

    (record,) = _read(audit_log)
    assert record["decision"] == "deny"
    assert "unknown metric" in record["reason"]
    # the offending arguments are captured for forensics, even though it was denied
    assert record["arguments"] == {"metric": "revenue_lol"}


def test_log_is_pure_json(audit_log):
    @audit.audited("list_tables")
    def tool():
        return [1, 2, 3]

    tool()
    # every non-blank line must parse as JSON (no stray protocol/plain-text noise)
    for line in audit_log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            json.loads(line)
