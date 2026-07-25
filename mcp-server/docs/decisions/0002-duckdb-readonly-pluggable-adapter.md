# ADR-0002: DuckDB (read-only) backend behind a pluggable adapter

- **Status:** Accepted

## Context

The server needs a warehouse that runs in a demo with **zero cloud cost and zero
credentials**, while staying honest that production would be Snowflake/BigQuery.

## Decision

Default backend is **DuckDB opened `read_only=True`** over the lakehouse Gold/marts
tables, exported into a local `warehouse.duckdb`. All access goes through a
`WarehouseAdapter` interface; the server, guards, semantic compiler, and audit
depend only on that interface. A `SnowflakeAdapter` stub documents the swap.

## Consequences

- `read_only=True` is **Layer 1** of defense-in-depth — the engine physically
  cannot write, the backstop the other layers sit in front of.
- The demo is reproducible with one `make export`; no secrets.
- Swapping to Snowflake is a new adapter class (a SELECT-only role is the Layer-1
  equivalent) — nothing in `guards/`, `semantic/`, or `server.py` changes.

## Alternatives

- **SQLite** — no analytical SQL / EXPLAIN story, weaker fit.
- **Connect straight to a cloud warehouse** — needs credentials and costs money;
  contradicts the zero-setup goal. Kept as the documented production target.
