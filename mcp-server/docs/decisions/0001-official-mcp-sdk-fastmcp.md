# ADR-0001: Official MCP SDK with the bundled FastMCP

- **Status:** Accepted

## Context

Two things called "FastMCP" exist: the one **bundled in the official Anthropic MCP
Python SDK** (`mcp.server.fastmcp.FastMCP`) and a separate, faster-moving
third-party package (`fastmcp`, v3+).

## Decision

Use the **official SDK** (`mcp`, pinned `>=1.27,<2`; resolved to 1.28.1) and its
bundled `FastMCP`. Tools are registered with `@mcp.tool(annotations=...)` and
carry protocol read-only hints; resources with `@mcp.resource(uri, ...)`.

## Consequences

- Guaranteed protocol compatibility with Claude Desktop / Cursor.
- Access to `ToolAnnotations` (readOnly/destructive/idempotent/openWorld) for the
  protocol layer of the defense model.
- Tests use the SDK's in-memory client/server session, so tools are verified over
  the real protocol, not just as functions.

## Alternatives

- **Third-party `fastmcp` v3** — more features, but not the reference
  implementation; for a portfolio piece aimed at a role naming "MCP server
  development", the official SDK is the defensible choice.
