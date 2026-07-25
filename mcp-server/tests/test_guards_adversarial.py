"""Adversarial guard suite — the heart of the governance story.

These are the attacks an LLM (or a prompt-injected user) could aim at the raw-SQL
escape hatch. Written FIRST against a stub that does no guarding (watch them
succeed = red), then the guards are built until every one flips to a specific
denial (green). Each test asserts *why* it was denied, not merely that it was.
"""

from __future__ import annotations

import pytest

from cfo_mcp.config import settings
from cfo_mcp.server import adapter
from cfo_mcp.guards.pipeline import assess, run_guarded

KNOWN = frozenset(t.fqn for t in adapter.list_tables())
CTX = dict(allowed_schemas=settings.allowed_schemas, known_fqns=KNOWN, max_rows=settings.max_rows)


def deny_reason(query: str) -> tuple[bool, str]:
    d = assess(query, **CTX)
    return d.allowed, d.reason.lower()


# --------------------------------------------------------------------------- #
# A well-formed query is allowed (guards must not be over-broad)
# --------------------------------------------------------------------------- #
def test_legitimate_query_is_allowed():
    d = assess("select region_sk, sum(net_revenue) from gold.fact_sales group by 1", **CTX)
    assert d.allowed is True, d.reason
    assert d.safe_sql and "limit" in d.safe_sql.lower()


def test_legitimate_cte_is_allowed():
    q = "with r as (select region_sk, net_revenue from gold.fact_sales) select * from r"
    assert assess(q, **CTX).allowed is True


# --------------------------------------------------------------------------- #
# Statement shape: prefix, stacked statements, comment obfuscation
# --------------------------------------------------------------------------- #
def test_stacked_statements_denied():
    allowed, reason = deny_reason("SELECT 1; DROP TABLE gold.fact_sales")
    assert allowed is False
    assert "statement" in reason  # multiple statements


def test_comment_obfuscated_ddl_with_semicolon_denied():
    allowed, reason = deny_reason("SELECT 1 /* */ ; DR/**/OP TABLE gold.fact_sales")
    assert allowed is False
    assert "statement" in reason


def test_comment_hidden_ddl_prefix_denied():
    allowed, reason = deny_reason("/* hide */ DROP TABLE gold.fact_sales")
    assert allowed is False
    assert "select" in reason  # must start with SELECT/WITH


def test_non_select_prefix_denied():
    allowed, reason = deny_reason("EXPLAIN SELECT 1")
    assert allowed is False
    assert "select" in reason


# --------------------------------------------------------------------------- #
# Write / DDL via the blocklist (even inside a CTE)
# --------------------------------------------------------------------------- #
def test_cte_hiding_a_delete_denied():
    allowed, reason = deny_reason("WITH x AS (SELECT 1) DELETE FROM gold.fact_sales")
    assert allowed is False
    assert "delete" in reason


def test_update_denied():
    allowed, reason = deny_reason("SELECT * FROM gold.fact_sales WHERE 1=(UPDATE gold.fact_sales SET net_revenue=0)")
    assert allowed is False
    assert "update" in reason


# --------------------------------------------------------------------------- #
# DuckDB-specific escapes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "query, needle",
    [
        ("ATTACH 'evil.db' AS e", "select"),                 # prefix (and blocklist ATTACH)
        ("INSTALL httpfs", "select"),
        ("LOAD httpfs", "select"),
        ("COPY (SELECT * FROM gold.fact_sales) TO 'C:/tmp/leak.csv'", "select"),
        ("SELECT * FROM read_csv('C:/Windows/win.ini')", "read_csv"),
        ("SELECT * FROM read_parquet('/etc/passwd')", "read_parquet"),
        ("SELECT * FROM glob('C:/*')", "glob"),
    ],
)
def test_duckdb_escapes_denied(query, needle):
    allowed, reason = deny_reason(query)
    assert allowed is False
    assert needle in reason


# --------------------------------------------------------------------------- #
# Schema allowlist (Layer 3) — reading outside gold/marts
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM meta.column_docs",
        "SELECT * FROM main.sqlite_master",
        "SELECT * FROM gold.fact_sales f JOIN meta.column_docs m ON true",
        "SELECT * FROM secret_schema.customers",
    ],
)
def test_out_of_allowlist_schema_denied(query):
    allowed, reason = deny_reason(query)
    assert allowed is False
    assert "allowlist" in reason or "schema" in reason


def test_unknown_table_in_allowlisted_schema_denied():
    allowed, reason = deny_reason("SELECT * FROM gold.does_not_exist")
    assert allowed is False
    assert "does_not_exist" in reason or "unknown" in reason


# --------------------------------------------------------------------------- #
# Unicode / whitespace tricks around the prefix check
# --------------------------------------------------------------------------- #
def test_zero_width_prefix_denied():
    # zero-width space before SELECT — not whitespace, so the prefix check fails
    allowed, reason = deny_reason("\u200bSELECT 1")
    assert allowed is False
    assert "select" in reason


def test_leading_ascii_whitespace_is_fine():
    assert assess("   \n\t select 1", **CTX).allowed is True


# --------------------------------------------------------------------------- #
# Row-limit and timeout enforcement (executed, not just analysed)
# --------------------------------------------------------------------------- #
def test_row_limit_enforced():
    outcome = run_guarded(adapter, "SELECT * FROM gold.fact_sales", timeout_s=10.0, **CTX)
    assert outcome.allowed is True
    assert outcome.result is not None
    assert len(outcome.result.rows) <= settings.max_rows  # 200k rows capped to 1000


def test_timeout_enforced():
    runaway = (
        "WITH RECURSIVE t(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM t WHERE i < 1000000000) "
        "SELECT count(*) FROM t"
    )
    outcome = run_guarded(adapter, runaway, timeout_s=0.3, **CTX)
    assert outcome.allowed is False
    assert "timeout" in outcome.reason.lower()
