"""Snowflake adapter — STUB.

This is intentionally unimplemented; it exists to show that the governance layer
(guards, semantic compiler, audit, tools) depends only on the `WarehouseAdapter`
interface, so pointing the server at Snowflake is a matter of implementing this
class — nothing in guards/, semantic/, or server.py changes.

Production notes captured here so the design intent is explicit:

* Layer 1 (engine) for Snowflake is a **role with SELECT-only grants on the
  `GOLD`/`MARTS` schemas** — the equivalent of DuckDB's read_only=True. Create a
  dedicated `CFO_MCP_RO` role, grant `USAGE` on the database/warehouse and
  `SELECT` on those schemas only, and connect as that role.
* `list_tables`/`get_columns` come from `INFORMATION_SCHEMA` exactly as here.
* `execute`'s statement timeout maps to `STATEMENT_TIMEOUT_IN_SECONDS`.
* The row-limit wrap and all of Layers 2-3 are engine-agnostic and reused as-is
  (sqlglot would parse with `dialect="snowflake"`).
"""

from __future__ import annotations

from .base import ColumnInfo, QueryResult, TableInfo, WarehouseAdapter


class SnowflakeAdapter(WarehouseAdapter):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "SnowflakeAdapter is a stub. Implement WarehouseAdapter against the "
            "Snowflake connector, connecting as a SELECT-only role on GOLD/MARTS. "
            "The guards, semantic layer, and tools are reused unchanged."
        )

    def list_tables(self) -> list[TableInfo]: ...
    def resolve_table(self, name: str) -> TableInfo | None: ...
    def get_columns(self, table: TableInfo) -> list[ColumnInfo]: ...
    def preview(self, table: TableInfo, n: int) -> QueryResult: ...
    def execute(self, sql: str, timeout_s: float, params: list | None = None) -> QueryResult: ...
    def explain(self, sql: str) -> str: ...
    def close(self) -> None: ...
