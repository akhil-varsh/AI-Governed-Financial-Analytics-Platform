# ADR-0001: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-07-24

## Context

This project makes several non-obvious engineering choices (medallion layering,
warehouse selection, two different SCD2 implementations, merge vs delete+insert).
In a consulting delivery, the *reasoning* behind a choice is as much a
deliverable as the code — it is what lets the client's team maintain the
platform after handover, and what an interviewer will probe.

## Decision

We keep short **Architecture Decision Records** in `docs/decisions/`, one file
per significant choice, numbered sequentially. Each ADR states the context, the
decision, the consequences, and — importantly — the **alternative that was
rejected and why**. ADRs are immutable once accepted; a later decision that
reverses an earlier one gets a new ADR that supersedes it.

## Consequences

- Every significant choice has a durable, reviewable rationale.
- New team members (and interviewers) can reconstruct *why*, not just *what*.
- Small overhead per decision — accepted as the cost of maintainability.

## Alternatives considered

- **A wiki / Confluence page** — rejected: drifts from the code, not versioned
  alongside it, dies when the engagement ends.
- **Comments in code only** — rejected: good for local "why", poor for
  cross-cutting choices that span many files.
