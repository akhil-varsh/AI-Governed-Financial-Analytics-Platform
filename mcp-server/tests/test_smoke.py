"""Phase 1 smoke tests: the adapter reads the warehouse, and `list_tables` works
end-to-end over a real (in-memory) MCP client/server session."""

from __future__ import annotations

import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as client_session

from cfo_mcp.config import settings
from cfo_mcp.adapters.duckdb import DuckDBAdapter
from cfo_mcp.server import mcp


def test_adapter_lists_governed_tables():
    adapter = DuckDBAdapter(settings.warehouse_path, settings.allowed_schemas)
    try:
        tables = {t.fqn: t for t in adapter.list_tables()}
    finally:
        adapter.close()

    # only the allowlisted schemas are visible
    assert {t.split(".")[0] for t in tables} == {"gold", "marts"}
    # a known fact with the expected volume and a real description
    assert tables["gold.fact_sales"].row_count == 200_000
    assert tables["gold.fact_sales"].description
    assert "marts.monthly_revenue_bridge" in tables


async def test_list_tables_over_mcp_protocol():
    async with client_session(mcp._mcp_server) as client:
        # the tool is advertised and marked read-only at the protocol level
        listing = await client.list_tools()
        tool = next(t for t in listing.tools if t.name == "list_tables")
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False

        # and it actually returns governed tables
        result = await client.call_tool("list_tables", {})
        assert result.isError is False
        payload = json.dumps(result.structuredContent)
        assert "gold.fact_sales" in payload
        assert "marts.gross_margin_by_segment" in payload
