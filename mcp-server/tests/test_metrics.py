"""Phase 5 — the semantic layer.

Proves the core governance claim: the caller asks for a *metric* and *how* to
slice/filter it, but never supplies SQL. Dimension/filter keys are validated
against the catalogue; filter values are parameterised, so an injection payload
in a value is inert.
"""

from __future__ import annotations

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as client_session

from cfo_mcp.server import mcp, semantic_layer
from cfo_mcp.semantic.compiler import compile_metric


def _unwrap(structured):
    if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
        return structured["result"]
    return structured


def _error_text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


# --------------------------------------------------------------------------- #
# Compiler unit tests (safety by construction)
# --------------------------------------------------------------------------- #
def test_filter_value_is_parameterised_not_concatenated():
    payload = "West'; DROP TABLE gold.fact_sales"
    compiled = compile_metric(semantic_layer, "net_revenue", None, {"region": payload}, "none")
    # the payload appears ONLY in params, never in the SQL text
    assert payload in compiled.params
    assert payload not in compiled.sql
    assert "?" in compiled.sql
    # and only allowlisted tables are referenced
    assert "drop" not in compiled.sql.lower()


def test_time_grain_expands_to_fiscal_dimensions():
    compiled = compile_metric(semantic_layer, "net_revenue", ["region"], None, "fiscal_quarter")
    assert compiled.dimensions == ["fiscal_year", "fiscal_quarter", "region"]


def test_unknown_metric_denied():
    with pytest.raises(Exception) as exc:
        compile_metric(semantic_layer, "revenue_lol", None, None, None)
    assert "unknown metric" in str(exc.value).lower()


def test_disallowed_dimension_denied():
    with pytest.raises(Exception) as exc:
        compile_metric(semantic_layer, "gl_expense_total", ["customer_segment"], None, "none")
    assert "not allowed" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# Tool-level tests over the MCP protocol
# --------------------------------------------------------------------------- #
async def test_list_metrics_returns_catalogue():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool("list_metrics", {})
        metrics = _unwrap(res.structuredContent)
        names = {m["name"] for m in metrics}
        assert {"net_revenue", "gross_margin_pct", "customer_count", "gl_expense_total"} <= names
        assert all(m["definition"] for m in metrics)


async def test_query_metric_net_revenue_by_region():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool(
            "query_metric", {"metric": "net_revenue", "dimensions": ["region"], "time_grain": "none"}
        )
        assert res.isError is False
        out = _unwrap(res.structuredContent)
        assert out["columns"] == ["region", "net_revenue"]
        assert out["row_count"] == 4
        assert "LIMIT" in out["compiled_sql"]


async def test_query_metric_gross_margin_in_range():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool(
            "query_metric", {"metric": "gross_margin_pct", "time_grain": "none"}
        )
        out = _unwrap(res.structuredContent)
        margin = out["rows"][0][0]
        assert 30 <= margin <= 45


async def test_query_metric_time_grain_by_fiscal_year():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool(
            "query_metric", {"metric": "customer_count", "time_grain": "fiscal_year"}
        )
        out = _unwrap(res.structuredContent)
        assert out["row_count"] == 3          # three fiscal years


async def test_query_metric_parameterised_filter():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool(
            "query_metric",
            {"metric": "net_revenue", "filters": {"region": "West"}, "time_grain": "none"},
        )
        out = _unwrap(res.structuredContent)
        assert out["row_count"] == 1          # single aggregate row for West


async def test_injection_in_filter_value_is_inert():
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool(
            "query_metric",
            {
                "metric": "net_revenue",
                "filters": {"region": "West'; DROP TABLE gold.fact_sales"},
                "time_grain": "none",
            },
        )
        assert res.isError is False           # treated as a (non-matching) value
        # and the table is unharmed
        tables = _unwrap((await client.call_tool("list_tables", {})).structuredContent)
        fact = next(t for t in tables if t["table"] == "gold.fact_sales")
        assert fact["row_count"] == 200_000


@pytest.mark.parametrize(
    "args, needle",
    [
        ({"metric": "no_such_metric"}, "unknown metric"),
        ({"metric": "net_revenue", "dimensions": ["cost_center"]}, "not allowed"),
        ({"metric": "net_revenue", "filters": {"secret": "x"}}, "not allowed"),
        ({"metric": "net_revenue", "time_grain": "weekly"}, "invalid time_grain"),
    ],
)
async def test_query_metric_denials(args, needle):
    async with client_session(mcp._mcp_server) as client:
        res = await client.call_tool("query_metric", args)
        assert res.isError is True
        assert needle in _error_text(res).lower()


async def test_metrics_catalogue_resource():
    async with client_session(mcp._mcp_server) as client:
        res = await client.read_resource("metrics://catalogue")
        text = res.contents[0].text
        assert "Metric Catalogue" in text
        assert "net_revenue" in text
        assert "gross_margin_pct" in text
