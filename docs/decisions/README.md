# Architecture Decision Records

Each ADR captures one significant choice: the context, the decision, its
consequences, and — importantly — the **alternative that was rejected and why**.
ADRs are immutable once accepted; a reversal gets a new ADR that supersedes the
old one. See [ADR-0001](0001-record-architecture-decisions.md) for the rationale.

| # | Decision | Headline |
| --- | --- | --- |
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Keep versioned ADRs with rejected alternatives. |
| [0002](0002-medallion-architecture.md) | Medallion architecture | Bronze/Silver/Gold/marts, not One Big Table. |
| [0003](0003-bigquery-portable-sql.md) | BigQuery + portable SQL | Vendor syntax isolated behind macros for cheap migration. |
| [0004](0004-uv-packaging.md) | `uv` for packaging | One tool for interpreter + venv + pinned lockfile. |
| [0005](0005-data-contracts-and-bronze-landing.md) | Data contracts + raw Bronze | Structural gate that allows dirt, rejects corruption; raw-string landing. |
| [0006](0006-silver-conformance-strategy.md) | Silver conformance | Dedup (no QUALIFY), seed-based region map, UNKNOWN keys, FX in Silver. |
| [0007](0007-gold-star-schema-and-scd2.md) | Gold star schema + SCD2 | Hand-written vs snapshot SCD2; merge on order_line_id. |
| [0008](0008-dual-engine-duckdb-bigquery.md) | Dual engine | DuckDB (local/CI) + BigQuery (documented) from one codebase. |
| [0009](0009-orchestration-and-ci.md) | Orchestration + CI | Dagster asset graph; secret-free DuckDB CI; cautious test selection. |

Per-phase "why" notes (interview-style, less formal) live in
[`../why/`](../why/).
