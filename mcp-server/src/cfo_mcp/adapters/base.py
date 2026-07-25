"""The warehouse adapter interface.

Every backend (DuckDB now; Snowflake/BigQuery later) implements this. The server
and the guard layer depend only on this interface, never on a concrete engine —
so swapping the backend is a drop-in change and the governance layer is reused
verbatim. The interface grows one phase at a time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableInfo:
    schema_name: str
    name: str
    row_count: int
    description: str

    @property
    def fqn(self) -> str:
        """Fully-qualified name, e.g. ``gold.fact_sales``."""
        return f"{self.schema_name}.{self.name}"


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    description: str
    sample_values: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple]


class WarehouseAdapter(ABC):
    """Read-only access to a governed warehouse."""

    @abstractmethod
    def list_tables(self) -> list[TableInfo]:
        """Tables in the allowlisted schemas, with row counts + descriptions."""

    @abstractmethod
    def resolve_table(self, name: str) -> TableInfo | None:
        """Resolve a user-supplied table name to a validated TableInfo, or None.

        The name is looked up against the set of allowlisted tables (from
        information_schema) — it is NEVER concatenated into SQL. A name that
        doesn't resolve to a real, allowlisted table returns None, which the
        caller turns into a denial. This is the identifier-safety boundary.
        """

    @abstractmethod
    def get_columns(self, table: TableInfo) -> list[ColumnInfo]:
        """Column name/type/nullability/description + a few sample values."""

    @abstractmethod
    def preview(self, table: TableInfo, n: int) -> QueryResult:
        """Up to ``n`` sample rows (n is clamped by the adapter)."""

    @abstractmethod
    def execute(self, sql: str, timeout_s: float, params: list | None = None) -> QueryResult:
        """Run an already-guarded SELECT with a hard statement timeout.

        ``params`` are bound positionally to ``?`` placeholders (used by the
        metric compiler for safe, parameterised filters). Raises ``TimeoutError``
        if the query exceeds ``timeout_s``. Assumes the SQL has passed the guards.
        """

    @abstractmethod
    def explain(self, sql: str) -> str:
        """Return the query plan (with estimated cardinalities) WITHOUT executing
        the query. Never uses EXPLAIN ANALYZE (which would run it)."""

    @abstractmethod
    def close(self) -> None:
        """Release the underlying connection."""
