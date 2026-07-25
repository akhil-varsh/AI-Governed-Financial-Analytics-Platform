"""The MCP server: a FastMCP app exposing read-only, governed finance tools.

Phase 1: discovery (`list_tables`).
Phase 2: schema (`get_schema`), preview (`preview_table`), and the
         `schema://tables` data-dictionary resource.

Every tool is annotated as read-only at the protocol level (Layer 4). Every tool
that takes a table name resolves it against the allowlisted set first; an
unknown or out-of-schema name is DENIED with a clear reason (the identifier-
safety boundary, formalised into a guard module in Phase 3).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .adapters.base import TableInfo
from .adapters.duckdb import DuckDBAdapter
from .audit import audited, configure_audit
from .config import settings
from .dictionary import build_data_dictionary
from .guards.pipeline import assess, run_guarded
from .semantic.catalogue import build_catalogue
from .semantic.compiler import compile_metric
from .semantic.model import SemanticError, load_semantic_layer

# --- protocol-level hints (Layer 4) ---------------------------------------- #
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

configure_audit(settings.audit_log_path)
adapter = DuckDBAdapter(settings.warehouse_path, settings.allowed_schemas)
semantic_layer = load_semantic_layer(settings.metrics_path)
mcp = FastMCP("cfo-mcp")

# The set of allowlisted, existing tables — passed to the guards so they can
# verify every table reference in a raw query.
_KNOWN_FQNS = frozenset(t.fqn for t in adapter.list_tables())


def _guard_ctx() -> dict:
    return dict(
        allowed_schemas=settings.allowed_schemas,
        known_fqns=_KNOWN_FQNS,
        max_rows=settings.max_rows,
    )


# --- output schemas -------------------------------------------------------- #
class TableSummary(BaseModel):
    table: str = Field(description="Fully-qualified name, e.g. 'gold.fact_sales'.")
    schema_name: str = Field(description="Schema (gold or marts).")
    name: str = Field(description="Table name.")
    row_count: int = Field(description="Number of rows.")
    description: str = Field(description="One-line business description.")


class ColumnDoc(BaseModel):
    name: str
    type: str
    nullable: bool
    description: str
    sample_values: list[str] = Field(description="A few example values from the column.")


class TableSchema(BaseModel):
    table: str
    description: str
    row_count: int
    columns: list[ColumnDoc]


class PreviewResult(BaseModel):
    table: str
    columns: list[str]
    rows: list[list[Any]]
    row_count_returned: int


class QueryResultOut(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int = Field(description="Rows returned (capped at the server row limit).")
    truncated: bool = Field(description="True if the row limit capped the result.")
    executed_sql: str = Field(description="The wrapped, row-limited SQL actually executed.")


class ExplainResult(BaseModel):
    plan: str = Field(description="The query plan with estimated cardinalities.")
    executed: bool = Field(description="Always false — the query was planned, not run.")
    planned_sql: str = Field(description="The guarded SQL that was planned.")


class MetricInfo(BaseModel):
    name: str
    label: str
    definition: str
    base_table: str
    unit: str
    allowed_dimensions: list[str]
    allowed_filters: list[str]
    default_time_grain: str
    owner: str


class MetricResult(BaseModel):
    metric: str
    definition: str
    unit: str
    dimensions: list[str] = Field(description="Columns the result is grouped by (incl. time grain).")
    time_grain: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    compiled_sql: str = Field(description="The parameterised SQL the metric compiled to (transparency).")


# --- helpers --------------------------------------------------------------- #
def _resolve_or_deny(table_name: str) -> TableInfo:
    """Resolve a user table name or raise a clear denial. Raising in a FastMCP
    tool returns an isError result carrying this message to the client."""
    resolved = adapter.resolve_table(table_name)
    if resolved is None:
        valid = ", ".join(t.fqn for t in adapter.list_tables())
        raise ValueError(
            f"Denied: '{table_name}' is not a known table in an allowlisted schema "
            f"(gold, marts). Valid tables: {valid}. Use list_tables to discover them."
        )
    return resolved


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return str(value)


# --- tools ----------------------------------------------------------------- #
@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "List every queryable table in the finance warehouse with its row count "
        "and a one-line description. Start here. Only the governed 'gold' and "
        "'marts' schemas are exposed."
    ),
)
@audited("list_tables")
def list_tables() -> list[TableSummary]:
    return [
        TableSummary(
            table=t.fqn,
            schema_name=t.schema_name,
            name=t.name,
            row_count=t.row_count,
            description=t.description,
        )
        for t in adapter.list_tables()
    ]


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Get the schema of one table: every column's name, type, nullability, "
        "business description, and a few sample values. Pass a name from "
        "list_tables (e.g. 'gold.fact_sales'). Use this before querying so you "
        "use real column names and understand the grain."
    ),
)
@audited("get_schema")
def get_schema(table: str) -> TableSchema:
    resolved = _resolve_or_deny(table)
    return TableSchema(
        table=resolved.fqn,
        description=resolved.description,
        row_count=resolved.row_count,
        columns=[
            ColumnDoc(
                name=c.name,
                type=c.data_type,
                nullable=c.nullable,
                description=c.description,
                sample_values=c.sample_values,
            )
            for c in adapter.get_columns(resolved)
        ],
    )


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Preview up to n sample rows (n<=50, default 10) from a table, to see "
        "what the data looks like. Pass a name from list_tables. This is a "
        "sample, not an aggregate — use query_metric for real numbers."
    ),
)
@audited("preview_table")
def preview_table(table: str, n: Annotated[int, Field(ge=1, le=50)] = 10) -> PreviewResult:
    resolved = _resolve_or_deny(table)
    result = adapter.preview(resolved, n)
    rows = [[_jsonable(v) for v in row] for row in result.rows]
    return PreviewResult(
        table=resolved.fqn,
        columns=result.columns,
        rows=rows,
        row_count_returned=len(rows),
    )


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "ESCAPE HATCH — run a raw read-only SQL query. Prefer query_metric for "
        "governed numbers; use this only for ad-hoc reads it can't express. The "
        "query must be a single SELECT/WITH over the gold/marts schemas; it is "
        "guarded (no writes, no DDL, no file access, one statement) and capped at "
        f"{settings.max_rows} rows with a {settings.query_timeout_s:.0f}s timeout. "
        "A blocked query returns a denial explaining which rule it violated."
    ),
)
@audited("execute_sql")
def execute_sql(query: str) -> QueryResultOut:
    outcome = run_guarded(
        adapter, query, timeout_s=settings.query_timeout_s, **_guard_ctx()
    )
    if not outcome.allowed:
        raise ValueError(f"Denied by guard: {outcome.reason}")
    result = outcome.result
    rows = [[_jsonable(v) for v in row] for row in result.rows]
    return QueryResultOut(
        columns=result.columns,
        rows=rows,
        row_count=len(rows),
        truncated=len(rows) >= settings.max_rows,
        executed_sql=outcome.executed_sql or "",
    )


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Return the query plan and estimated cost for a SQL query WITHOUT running "
        "it. Same guards as execute_sql. Use this to sanity-check a heavy query "
        "before executing it."
    ),
)
@audited("explain_query")
def explain_query(query: str) -> ExplainResult:
    decision = assess(query, **_guard_ctx())
    if not decision.allowed:
        raise ValueError(f"Denied by guard: {decision.reason}")
    plan = adapter.explain(decision.safe_sql)
    return ExplainResult(plan=plan, executed=False, planned_sql=decision.safe_sql)


# --- semantic layer (the preferred query path) ----------------------------- #
@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "List the governed metric catalogue: each metric's name, plain-English "
        "definition, base table, unit, and the dimensions/filters it allows. "
        "Read this (or the metrics://catalogue resource) and use query_metric — "
        "it's the correct, governed way to get numbers."
    ),
)
@audited("list_metrics")
def list_metrics() -> list[MetricInfo]:
    return [
        MetricInfo(
            name=name,
            label=m.label,
            definition=m.definition,
            base_table=m.base_table,
            unit=m.unit,
            allowed_dimensions=m.allowed_dimensions,
            allowed_filters=m.allowed_filters,
            default_time_grain=m.default_time_grain,
            owner=m.owner,
        )
        for name, m in semantic_layer.metrics.items()
    ]


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "PREFERRED WAY TO GET NUMBERS. Run a governed metric from the catalogue "
        "(see list_metrics), optionally sliced by dimensions, narrowed by filters, "
        "and bucketed by a time grain. The metric's definition is fixed and "
        "reviewed, so you cannot get the revenue/margin formula wrong. Filter "
        "values are parameterised. Example: metric='net_revenue', "
        "dimensions=['region'], filters={'fiscal_year': 2023}, time_grain='fiscal_quarter'."
    ),
)
@audited("query_metric")
def query_metric(
    metric: str,
    dimensions: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    time_grain: str | None = None,
) -> MetricResult:
    try:
        compiled = compile_metric(semantic_layer, metric, dimensions, filters, time_grain)
    except SemanticError as exc:
        raise ValueError(f"Denied: {exc}")

    outcome = run_guarded(
        adapter, compiled.sql, timeout_s=settings.query_timeout_s, params=compiled.params, **_guard_ctx()
    )
    if not outcome.allowed:
        raise ValueError(f"Denied by guard: {outcome.reason}")

    rows = [[_jsonable(v) for v in row] for row in outcome.result.rows]
    return MetricResult(
        metric=compiled.metric,
        definition=compiled.definition,
        unit=compiled.unit,
        dimensions=compiled.dimensions,
        time_grain=compiled.time_grain,
        columns=outcome.result.columns,
        rows=rows,
        row_count=len(rows),
        compiled_sql=outcome.executed_sql or "",
    )


# --- resources ------------------------------------------------------------- #
@mcp.resource(
    "schema://tables",
    name="Data dictionary",
    description="Full data dictionary (all governed tables, columns, types, descriptions) as markdown.",
    mime_type="text/markdown",
)
def data_dictionary() -> str:
    return build_data_dictionary(adapter)


@mcp.resource(
    "metrics://catalogue",
    name="Metric catalogue",
    description="The governed semantic-layer metric definitions as markdown.",
    mime_type="text/markdown",
)
def metrics_catalogue() -> str:
    return build_catalogue(semantic_layer)


def main() -> None:
    """Console entrypoint: run over stdio (how Claude Desktop launches it)."""
    mcp.run()


if __name__ == "__main__":
    main()
