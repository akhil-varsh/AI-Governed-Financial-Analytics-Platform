# Why — Phase 6: Audit logging

Interview-defensible notes.

## "What does the audit layer add — it doesn't block anything?"

Correct, and that's the point of naming it a *separate* layer. Layers 1–3
**prevent**; Layer 5 provides **accountability and detection**. Before a finance
or compliance team lets an LLM touch the warehouse, they'll ask: who asked what,
what was blocked and why, and can we prove it after the fact? The audit log
answers all three. Every tool call is one structured JSON line with timestamp,
tool, arguments, generated SQL, rows returned, latency, and the **allow/deny
decision + reason**. It's the "verify" in trust-but-verify.

## "Why log to stderr and a file — the spec said stdout?"

Because this is an MCP **stdio** server: stdout is the JSON-RPC transport between
the server and Claude Desktop. Writing audit JSON to stdout would interleave with
protocol frames and **break the connection**. Diagnostics on a stdio server must
go to stderr (and/or a file). This is a small thing that would fail immediately in
a real deployment — so I changed it and flagged it rather than following the spec
into a bug.

## "Why a dedicated logger instead of the root logger?"

My first cut used `logging.basicConfig(force=True)`, which hijacked the root
logger — and the MCP SDK's own `"Processing request..."` INFO logs started
landing in `audit.log` as non-JSON lines, corrupting the stream. The fix is a
dedicated `cfo_mcp.audit` logger with `propagate=False` and its own handlers, so
**only** audit events reach the audit log. There's a test asserting the log is
pure JSON, precisely so that regression can't come back.

## "You log the arguments even when a call is denied — why?"

Forensics. The most interesting line in a security log is the **blocked** one: the
malicious query someone tried. If I only logged allowed calls, I'd throw away
exactly the evidence an incident review needs. So a denial is logged with its
arguments and the reason it was refused — e.g. the raw `SELECT * FROM
meta.column_docs` that the schema allowlist stopped.

## "What does the analysis script show, and why does it matter?"

`scripts/analyze_audit.py` turns the JSON lines into a SOC-style summary: call
volume, allow/deny split, **top denial reasons**, most-used tools/metrics, and the
slowest calls. In the demo run it immediately surfaced that ~half the calls were
denials (the adversarial tests) and *why* each was blocked. That's the difference
between "we have logs somewhere" and "we can answer a question about them in ten
seconds." Structured JSON is what makes that trivial — no regex-scraping of
free-text logs.

## The honest framing

Audit prevents nothing on its own. Its value is entirely in accountability,
detection, and post-hoc analysis — which is why it's the outermost layer,
wrapping (not replacing) the guards that do the preventing.
