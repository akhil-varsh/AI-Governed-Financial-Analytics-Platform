# ADR-0004: `uv` for environment and dependency management

- **Status:** Accepted
- **Date:** 2026-07-24

## Context

Reproducibility is a non-negotiable requirement, including a **pinned
lockfile**. The stack pins Python to 3.11 (dbt-core/dbt-bigquery and Dagster do
not yet support the newest CPython on this machine, which defaults to 3.14). We
need one tool that manages the Python version, the virtualenv, and a fully
resolved lockfile, and that CI can restore identically.

## Decision

Use **`uv`**:

- `uv python install 3.11` provisions the exact interpreter, independent of
  whatever Python the machine defaults to (here, 3.14).
- `.python-version` pins the interpreter for the repo.
- `pyproject.toml` declares dependencies, split into the core ingestion runtime,
  a `platform` extra (dbt + Dagster), and a `dev` extra (sqlfluff, pytest,
  pre-commit).
- `uv.lock` is the committed, fully-resolved lockfile — CI restores it verbatim.

## Consequences

- One fast tool for interpreter + venv + lockfile; trivial cold-start in CI.
- Extras keep a slim ingestion-only environment separable from the heavy
  transformation stack.
- `uv` emits a harmless warning that the `dbt` namespace is provided by both
  `dbt-core` and `dbt-bigquery`; documented and ignored.

## Alternatives considered

- **Poetry** — mature and popular, but slower resolves, and it does not manage
  the Python interpreter version itself (needs pyenv alongside). `uv` folds both
  jobs into one tool.
- **pip + requirements.txt + venv** — lowest common denominator; manual pinning,
  no interpreter management, weaker reproducibility guarantees.
- **conda** — heavyweight, and not how the analytics-engineering ecosystem
  (dbt/Dagster) is typically packaged.
