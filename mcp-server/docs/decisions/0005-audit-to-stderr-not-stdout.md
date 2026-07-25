# ADR-0005: Audit logs to stderr + file, never stdout

- **Status:** Accepted

## Context

The brief asked for audit logs to "file and stdout." But this server speaks MCP
over **stdio**: stdout carries the JSON-RPC protocol frames between the server and
Claude Desktop.

## Decision

Write the structured JSON audit log to a **file and to stderr**, never stdout. Use
a **dedicated, non-propagating `cfo_mcp.audit` logger** so the MCP SDK's own logs
don't leak into the audit stream.

## Consequences

- The MCP transport is never corrupted; the server works in Claude Desktop.
- The audit log is pure JSON (there is a test asserting this), so
  `analyze_audit.py` — and any real log pipeline — can parse it trivially.
- Every tool call (allow and deny) is one JSON line with args, generated SQL,
  rows, latency, decision, and reason. Arguments are logged even on denial, for
  forensics.

## Alternatives

- **stdout as specified** — would interleave with protocol frames and break the
  connection. Rejected as an outright bug (flagged, not silently followed).
- **Root logger via `basicConfig`** — my first attempt; it captured the MCP SDK's
  INFO logs into the audit file. Rejected for the dedicated logger.
