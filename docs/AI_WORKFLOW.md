# AI-assisted workflow

This project was built with AI pair-programming (Claude Code) under human
direction. This document is deliberately honest about *how*, because a Data & AI
Engineer should be able to use AI tools well **and** explain what they own.

## How the work was structured

The build ran in **eight explicit phases** (scaffold → contracts/ingestion →
Silver → Gold → marts → tests/docs → orchestration/CI → docs), with a review
checkpoint at the end of each. AI did not run ahead; each phase was summarised,
inspected, and accepted before the next began. Each phase also produced a
`docs/why/` note stating the key decisions and the rejected alternatives, so the
reasoning is recoverable and defensible.

## The principle: AI types, the engineer verifies

Every claim in this repo is backed by a command that was actually run — not
asserted. Concretely, during the build we **executed and confirmed**:

- the GL reconciles to sales revenue (to $0.12 on $173M) — in pandas *and* in the
  warehouse;
- the full dependency graph resolves on Python 3.11 and the lockfile builds;
- `dbt build` is green at each layer (217 nodes; 195 tests);
- ingestion is idempotent (re-run skips loaded batches) and `fact_sales` is
  idempotent (re-run holds 200k/200k);
- both SCD2 histories match the injected changes, and a point-in-time join
  attributes sales to the segment as-was;
- Dagster loads and the job runs end-to-end (`RUN_SUCCESS`);
- the CI recipe is green — run locally before pushing.

## Bugs the verification caught (and fixed)

Running things, rather than trusting that they "look right", surfaced real bugs:

1. A data contract wrongly required `discount_amount >= 0`, which failed on
   returns (negative discount). → Loosened the contract, not the data.
2. `CUST-000002`'s middle master extract was unpinned and leaked a random
   segment, creating a spurious third SCD2 version. → Pinned all three special
   customers explicitly.
3. The revenue-bridge test asserted `gross − discounts + returns = net` and
   failed on 34/36 months by cents (independent per-line rounding). → Tested the
   identity that's exact by construction (`sales_net + returns = net`).
4. A cross-layer singular test ran under dbt's default *eager* selection before
   its model existed, breaking the split CI build. → `--indirect-selection
   cautious` on the intermediate build.

None of these were visible on paper; all were obvious on execution.

## What stays a human decision

- **Architecture** — the medallion split, star-schema grain, the two SCD2
  strategies, the portability seam, and the dual-engine (BigQuery/DuckDB) call are
  design choices owned and defended in the ADRs and `why/` notes.
- **Business correctness** — the February fiscal calendar, FX conversion, the
  allow-legal / reject-corrupt line for contracts, and the materiality tolerance
  on the tie-out are judgement calls checked against the business definitions.
- **Verification** — deciding *what* to prove, and actually proving it.

AI accelerated the typing; the engineer owns the thinking and the verification.
