# AI-assisted workflow

Built with AI pair-programming (Claude Code) under human direction. This is an
honest account of how, because a Data & AI Engineer should use AI tools well
**and** be able to explain what they own.

## Structure

Seven explicit phases with a review checkpoint after each: scaffold → schema tools
→ guards (tests-first) → escape-hatch tools → semantic layer → audit → docs. Each
phase produced a `docs/why/` note stating the decisions and rejected alternatives,
so the reasoning is recoverable and defensible.

## AI types, the engineer verifies

Every claim is backed by a command that was run, not asserted. During the build we
**executed and confirmed**:

- the `mcp>=1.27` pin actually resolves (to 1.28.1) and `ToolAnnotations` has the
  four hints the design needs — checked before building on them;
- `list_tables` works end-to-end over the real (in-memory) MCP protocol;
- the guards: **22 attacks succeed against a stub, then 25 pass** once built;
- the injection-as-value payload lands **only in `params`**, and the table is
  unharmed;
- metrics reconcile to the lakehouse (margin 37.8%, region revenue, expense total);
- the audit log is **pure JSON** and the analysis script summarises it.

Final: **62 tests**, all green.

## Corrections I made rather than following the spec into a bug

- **Audit to stderr, not stdout** — stdout is the MCP stdio transport; logging
  there would break the client. Changed and documented (ADR-0005).
- **Dedicated non-propagating audit logger** — my first cut leaked the MCP SDK's
  own logs into the audit file; a test now guards against regression.
- **Identifier safety in Phase 2, not deferred to Phase 3** — I wouldn't ship an
  injectable tool for even one phase; the "watch it break" demo lives on the
  `execute_sql` guards where it belongs.

## What stays a human decision

- **The security model** — the five layers, what each stops, and the honest gaps
  (residual risks in the threat model) are owned and defensible.
- **The semantic design** — that governed metrics, not free SQL, are the primary
  path; and encoding SCD2/fiscal correctness into the catalogue.
- **Verification** — deciding what to prove (the attacks, the reconciliations, the
  pure-JSON log) and proving it.

AI accelerated the typing; the engineer owns the threat model, the semantic
design, and the verification.
