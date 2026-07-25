# Why — Phase 1: Scaffold, adapter, and a working `list_tables`

Interview-defensible notes.

## "What is this project actually demonstrating?"

Not "an LLM writes SQL." It's the **governance layer** that makes letting an LLM
near a finance warehouse safe. Phase 1 lays the two foundations that everything
else builds on: a **read-only adapter** the engine itself can't write through, and
an **MCP server** whose tools are declared read-only at the protocol level. The
interesting parts (semantic metric catalogue, five-layer defense, audit trail)
sit on top of this in later phases.

## "Why the bundled `mcp.server.fastmcp.FastMCP`, not the third-party `fastmcp`?"

The official Anthropic MCP Python SDK (`mcp`, pinned `>=1.27,<2`; resolved to
1.28.1) *bundles* FastMCP. The separate `fastmcp` v3 package is a different,
faster-moving project. For a portfolio piece aimed at a role that names "MCP
server development," using the **official SDK** is the defensible, standard choice
and guarantees protocol compatibility with Claude Desktop.

## "Why DuckDB read-only, and why an adapter interface?"

- **read-only** (`duckdb.connect(..., read_only=True)`) is **Layer 1** of
  defense-in-depth: even if every application guard were bypassed, the engine
  physically cannot write. It's the backstop the other four layers sit in front
  of.
- **The adapter interface** (`WarehouseAdapter`) means the server and the guards
  depend on an abstraction, not on DuckDB. Swapping in Snowflake/BigQuery later is
  a new adapter class — the governance layer is reused verbatim. That's the
  "pluggable backend" the brief asks for, and it keeps the demo zero-cost/zero-
  credential while staying honest about production.

## "Why export the Gold tables into a separate file?"

The MCP server ships its **own** self-contained `warehouse.duckdb`, reproducible
with `make export` from the lakehouse. This decouples the two projects, and the
export renames the lakehouse's `northwind_dev_gold`/`_marts` schemas to the clean,
allowlisted `gold`/`marts` the server governs — so the **schema allowlist**
(Layer 3, arriving fully in Phase 3) has exactly two obvious targets.

## "Why protocol annotations already, on a read-only listing tool?"

Because they're the contract a client reads *before* calling. Marking every tool
`readOnlyHint=True, destructiveHint=False, idempotentHint=True,
openWorldHint=False` (Layer 4) tells Claude Desktop these tools are safe to call
freely and never mutate state. Setting the habit from tool #1 means no tool ever
ships without its safety contract.

## What Phase 1 proves (verified)

- The adapter sees **only** `gold`/`marts` (allowlist working at the discovery
  layer), and `gold.fact_sales` has the expected 200,000 rows.
- `list_tables` works **end-to-end over the real MCP protocol** (in-memory
  client↔server session), advertised with the read-only annotations and returning
  the governed tables.

## What is deliberately NOT here yet

No schema/preview tools (Phase 2), no SQL guards or adversarial tests (Phase 3),
no `execute_sql` (Phase 4), no metric catalogue (Phase 5), no audit log (Phase 6).
`list_tables` reads discovery metadata only — it takes no user input, so it has no
attack surface to guard yet.
