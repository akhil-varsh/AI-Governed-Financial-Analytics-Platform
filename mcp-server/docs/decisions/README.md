# Architecture Decision Records

Each ADR records one significant choice — context, decision, consequences, and the
rejected alternative.

| # | Decision |
| - | -------- |
| [0001](0001-official-mcp-sdk-fastmcp.md) | Official MCP SDK with the bundled FastMCP (not third-party `fastmcp`). |
| [0002](0002-duckdb-readonly-pluggable-adapter.md) | DuckDB `read_only=True` behind a pluggable `WarehouseAdapter`. |
| [0003](0003-semantic-metric-catalogue.md) | A YAML metric catalogue as the primary query path. |
| [0004](0004-five-layer-defense-in-depth.md) | Five-layer defense-in-depth for the raw-SQL path, tests-first. |
| [0005](0005-audit-to-stderr-not-stdout.md) | Audit to stderr + file, never stdout (MCP stdio constraint). |

Per-phase "why" notes (interview-style) live in [`../why/`](../why/).
