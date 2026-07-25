# AI-assisted workflow

This project was built with AI pair-programming (Claude Code) under human
direction. This document is deliberately honest about *how*, because a Data & AI
Engineer should be able to use AI tools well **and** explain what they own.

## How the work was structured

The build runs in **explicit phases** (scaffold → contracts/ingestion → Silver →
Gold → marts → tests/docs → orchestration/CI → docs), with a review checkpoint
at the end of each phase. AI does not run ahead; each phase is inspected and
accepted before the next begins. This keeps every change reviewable and keeps me
(the engineer) in control of the design, not just the output.

## What AI did well here

- Scaffolding boilerplate (project layout, Makefile, dbt config) quickly and
  consistently.
- Writing the seeded synthetic-data generator, including the GL tie-out logic.
- Drafting documentation and ADRs from a stated rationale.

## What stays a human decision

- **Architecture** — the medallion split, the star-schema grain, SCD strategy,
  and the portability seam are design choices I own and can defend (see the
  ADRs and the per-phase `why/` notes).
- **Verification** — every generated artefact is run and checked. Phase 1
  examples: the generator's tie-out reconciliation was executed and confirmed
  (~$173M GL revenue == sales net revenue); the full dependency graph was
  resolved on Python 3.11; `dbt parse` was run to confirm the project compiles.
- **Correctness of business logic** — fiscal calendar, currency conversion, and
  data-quality rules are checked against the business definitions, not taken on
  faith.

## Principle

AI accelerates the *typing*; the engineer owns the *thinking* and the
*verification*. Every claim in this repo ("it ties out", "it's idempotent", "the
tests pass") is backed by a command that was actually run, not asserted.
