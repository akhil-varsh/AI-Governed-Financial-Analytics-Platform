"""Scripted demo conversation — drives the MCP server through a realistic CFO
session, for recording a GIF or a quick manual smoke test.

    uv run python scripts/demo.py           # paced for recording
    uv run python scripts/demo.py --fast    # no pauses

It walks through discovery, governed metric queries, a raw-SQL escape hatch, and
two blocked attacks — showing that the governance holds — then points at the
audit log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time

from mcp.shared.memory import create_connected_server_and_client_session as client_session

from cfo_mcp import audit
from cfo_mcp.server import mcp


def _quiet_for_demo() -> None:
    """Keep the demo terminal clean: silence MCP SDK INFO logs and drop the audit
    logger's stderr handler (the FILE handler stays, so analyze_audit still works)."""
    logging.getLogger("mcp").setLevel(logging.WARNING)
    audit_logger = logging.getLogger(audit._AUDIT_LOGGER_NAME)
    audit_logger.handlers = [h for h in audit_logger.handlers if isinstance(h, logging.FileHandler)]

FAST = "--fast" in sys.argv
DIM, BOLD, GREEN, RED, CYAN, YELLOW, RESET = (
    "\033[2m", "\033[1m", "\033[32m", "\033[31m", "\033[36m", "\033[33m", "\033[0m"
)


def pause(seconds: float) -> None:
    if not FAST:
        time.sleep(seconds)


def user(text: str) -> None:
    pause(0.6)
    print(f"\n{BOLD}{CYAN}CFO ▸{RESET} {text}")
    pause(0.5)


def call(name: str, args: dict) -> None:
    print(f"{DIM}   → tool: {name}({json.dumps(args)}){RESET}")
    pause(0.4)


def _unwrap(structured):
    if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
        return structured["result"]
    return structured


async def run() -> None:
    async with client_session(mcp._mcp_server) as client:
        print(f"{BOLD}=== CFO MCP server — governed finance Q&A ==={RESET}")

        # 1. discovery
        user("What data can I look at?")
        call("list_tables", {})
        tables = _unwrap((await client.call_tool("list_tables", {})).structuredContent)
        for t in tables[:6]:
            print(f"     {GREEN}•{RESET} {t['table']:<32} {t['row_count']:>8,} rows")
        print(f"     {DIM}… {len(tables)} governed tables in gold + marts{RESET}")

        # 2. governed metric
        user("What was net revenue by region?")
        args = {"metric": "net_revenue", "dimensions": ["region"], "time_grain": "none"}
        call("query_metric", args)
        out = _unwrap((await client.call_tool("query_metric", args)).structuredContent)
        for row in out["rows"]:
            print(f"     {GREEN}•{RESET} {row[0]:<12} ${row[1]:>15,.2f}")
        print(f"     {DIM}definition: {out['definition']}{RESET}")

        # 3. margin by segment
        user("And gross margin % by customer segment?")
        args = {"metric": "gross_margin_pct", "dimensions": ["customer_segment"], "time_grain": "none"}
        call("query_metric", args)
        out = _unwrap((await client.call_tool("query_metric", args)).structuredContent)
        for row in out["rows"]:
            print(f"     {GREEN}•{RESET} {row[0]:<12} {row[1]:>6}%")

        # 4. raw SQL escape hatch (allowed)
        user("Run a quick custom one: order lines by channel.")
        sql = ("select ch.channel_name, count(*) as lines from gold.fact_sales f "
               "join gold.dim_channel ch on f.channel_sk = ch.channel_sk group by 1 order by 2 desc")
        call("execute_sql", {"query": sql})
        out = _unwrap((await client.call_tool("execute_sql", {"query": sql})).structuredContent)
        for row in out["rows"]:
            print(f"     {GREEN}•{RESET} {row[0]:<12} {row[1]:>8,}")

        # 5. attacks — blocked
        user("(malicious) Drop the sales table.")
        call("execute_sql", {"query": "DROP TABLE gold.fact_sales"})
        res = await client.call_tool("execute_sql", {"query": "DROP TABLE gold.fact_sales"})
        print(f"     {RED}✗ DENIED:{RESET} {' '.join(getattr(c, 'text', '') for c in res.content)}")

        user("(malicious) Read a file off the server's disk.")
        q = "select * from read_csv('C:/Windows/win.ini')"
        call("execute_sql", {"query": q})
        res = await client.call_tool("execute_sql", {"query": q})
        print(f"     {RED}✗ DENIED:{RESET} {' '.join(getattr(c, 'text', '') for c in res.content)}")

        # 6. wrap up
        pause(0.6)
        print(f"\n{BOLD}{YELLOW}Every call above — allowed and denied — was logged as JSON.{RESET}")
        print(f"{DIM}   run: uv run python scripts/analyze_audit.py{RESET}\n")


if __name__ == "__main__":
    _quiet_for_demo()
    asyncio.run(run())
