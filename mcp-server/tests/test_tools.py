"""Phase 2 tool tests, over a real in-memory MCP session.

Includes the identifier-safety cases: an unknown table, a table in a non-
allowlisted schema, and a SQL-injection attempt via the table argument are all
DENIED — and the raw argument never reaches SQL (it simply fails to resolve).
"""

from __future__ import annotations

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as client_session

from cfo_mcp.server import mcp


def _unwrap(structured):
    """FastMCP wraps list returns under {'result': ...}; objects are returned as-is."""
    if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
        return structured["result"]
    return structured


def _error_text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


async def test_get_schema_has_columns_descriptions_and_samples():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool("get_schema", {"table": "gold.fact_sales"})
        assert res.isError is False
        schema = _unwrap(res.structuredContent)
        names = {c["name"] for c in schema["columns"]}
        assert {"order_line_id", "net_revenue", "gross_profit"} <= names
        # descriptions come from the dbt manifest; samples from real data
        assert any(c["description"] for c in schema["columns"])
        assert any(c["sample_values"] for c in schema["columns"])


async def test_preview_returns_rows_and_columns():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool(
            "preview_table", {"table": "marts.monthly_revenue_bridge", "n": 5}
        )
        assert res.isError is False
        preview = _unwrap(res.structuredContent)
        assert preview["row_count_returned"] == 5
        assert "net_revenue" in preview["columns"]


async def test_preview_n_over_limit_is_rejected():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool("preview_table", {"table": "gold.dim_region", "n": 9999})
        assert res.isError is True  # violates the le=50 input constraint


@pytest.mark.parametrize(
    "bad_table",
    [
        "gold.secret_table",                              # unknown table
        "meta.column_docs",                               # exists but NOT allowlisted
        "information_schema.tables",                      # engine schema, not allowlisted
        "gold.fact_sales; drop table gold.fact_sales",    # injection via table name
        "gold.fact_sales--",                              # comment trick
    ],
)
async def test_bad_table_names_are_denied(bad_table):
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool("get_schema", {"table": bad_table})
        assert res.isError is True
        assert "Denied" in _error_text(res)


async def test_data_dictionary_resource_is_markdown():
    async with client_session(mcp._mcp_server) as client:
        res = await client.read_resource("schema://tables")
        text = res.contents[0].text
        assert "# Finance Warehouse — Data Dictionary" in text
        assert "`gold.fact_sales`" in text
        assert "net_revenue" in text
        # meta schema must NOT leak into the dictionary
        assert "meta.column_docs" not in text


# --------------------------------------------------------------------------- #
# Phase 4 — execute_sql + explain_query behind the guards
# --------------------------------------------------------------------------- #
async def test_execute_sql_runs_a_governed_query():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool(
            "execute_sql",
            {"query": "select region_sk, sum(net_revenue) as rev from gold.fact_sales group by 1"},
        )
        assert res.isError is False
        out = _unwrap(res.structuredContent)
        assert out["row_count"] == 4           # four regions with sales
        assert "LIMIT" in out["executed_sql"]  # the guard wrapped it


async def test_execute_sql_enforces_row_limit():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool("execute_sql", {"query": "select * from gold.fact_sales"})
        out = _unwrap(res.structuredContent)
        assert out["row_count"] == 1000        # 200k capped
        assert out["truncated"] is True


@pytest.mark.parametrize(
    "query",
    [
        "select * from meta.column_docs",                    # out-of-allowlist schema
        "select 1; drop table gold.fact_sales",              # stacked
        "select * from read_csv('C:/Windows/win.ini')",      # file access
        "delete from gold.fact_sales",                       # write
    ],
)
async def test_execute_sql_denies_attacks(query):
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool("execute_sql", {"query": query})
        assert res.isError is True
        assert "Denied by guard" in _error_text(res)


async def test_explain_query_plans_without_executing():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool(
            "explain_query", {"query": "select * from gold.fact_sales where region_sk = 'x'"}
        )
        assert res.isError is False
        out = _unwrap(res.structuredContent)
        assert out["executed"] is False
        assert out["plan"]                      # a non-empty plan came back


async def test_explain_query_is_also_guarded():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool("explain_query", {"query": "select * from meta.column_docs"})
        assert res.isError is True
        assert "Denied by guard" in _error_text(res)
