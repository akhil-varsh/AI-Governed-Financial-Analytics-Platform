"""Compile a metric request into safe, parameterised SQL.

Safety model:
  * The metric expression, dimension SQL, and filter SQL all come from the
    reviewed YAML — never from the caller.
  * Dimension and filter *keys* are validated against the metric's allowlist; an
    unknown or disallowed key is a denial (SemanticError), not a silent ignore.
  * Filter *values* are bound as query PARAMETERS (`?`), never concatenated. A
    value like "West'; DROP TABLE ..." becomes a harmless string literal that
    simply matches nothing.
  * The compiled SQL is still run through the SQL guards before execution.

So the caller controls *which* governed metric and *how* it's sliced/filtered —
but not the SQL. That's the whole point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import Metric, SemanticError, SemanticLayer, TIME_GRAINS

_BASE_ALIAS = "base"


@dataclass
class CompiledQuery:
    metric: str
    definition: str
    unit: str
    dimensions: list[str]
    time_grain: str
    sql: str
    params: list[Any] = field(default_factory=list)


def _coerce(value: Any, ftype: str) -> Any:
    try:
        if ftype == "int":
            return int(value)
        if ftype == "number":
            return float(value)
        if ftype == "bool":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("true", "1", "yes")
        # string / date pass through as text; date comparison casts in-engine
        return str(value)
    except (TypeError, ValueError) as exc:
        raise SemanticError(f"filter value {value!r} is not a valid {ftype}") from exc


def compile_metric(
    layer: SemanticLayer,
    metric_name: str,
    dimensions: list[str] | None,
    filters: dict[str, Any] | None,
    time_grain: str | None,
) -> CompiledQuery:
    metric: Metric | None = layer.metrics.get(metric_name)
    if metric is None:
        raise SemanticError(
            f"unknown metric '{metric_name}'. Available: {sorted(layer.metrics)}"
        )

    dimensions = list(dimensions or [])
    filters = dict(filters or {})
    grain = time_grain or metric.default_time_grain
    if grain not in TIME_GRAINS:
        raise SemanticError(f"invalid time_grain '{grain}'. Valid: {sorted(TIME_GRAINS)}")

    # Group-by dimensions = time-grain dims first, then requested dims (deduped).
    group_dims: list[str] = list(TIME_GRAINS[grain])
    for dim in dimensions:
        if dim not in group_dims:
            group_dims.append(dim)

    # Validate every group dimension against the metric's allowlist + groupability.
    for dim in group_dims:
        if dim not in metric.allowed_dimensions:
            raise SemanticError(
                f"dimension '{dim}' is not allowed for metric '{metric_name}'. "
                f"Allowed: {metric.allowed_dimensions}"
            )
        if not layer.dimensions[dim].groupable:
            raise SemanticError(f"dimension '{dim}' cannot be grouped by")

    # Validate filters against the allowlist.
    for key in filters:
        if key not in metric.allowed_filters:
            raise SemanticError(
                f"filter '{key}' is not allowed for metric '{metric_name}'. "
                f"Allowed: {metric.allowed_filters}"
            )

    # --- assemble --------------------------------------------------------- #
    joins: list[str] = []
    seen: set[str] = set()

    def add_join(clause: str | None) -> None:
        if not clause:
            return
        rendered = clause.replace("{base}", _BASE_ALIAS)
        if rendered not in seen:
            seen.add(rendered)
            joins.append(rendered)

    # metric-required joins (e.g. dim_customer for customer counts)
    for key in metric.required_joins:
        add_join(layer.dimensions[key].join)

    select_parts: list[str] = []
    for dim in group_dims:
        d = layer.dimensions[dim]
        add_join(d.join)
        select_parts.append(f"{d.sql.replace('{base}', _BASE_ALIAS)} as {dim}")
    select_parts.append(f"{metric.expression} as {metric_name}")

    where_parts: list[str] = []
    params: list[Any] = []
    if metric.base_filter:
        where_parts.append(f"({metric.base_filter})")
    for key, value in filters.items():
        f = layer.filters[key]
        add_join(f.join)
        col = f.sql.replace("{base}", _BASE_ALIAS)
        if isinstance(value, (list, tuple)):
            if not value:
                raise SemanticError(f"filter '{key}' has an empty value list")
            placeholders = ", ".join("?" for _ in value)
            where_parts.append(f"{col} in ({placeholders})")
            params.extend(_coerce(v, f.type) for v in value)
        else:
            where_parts.append(f"{col} = ?")
            params.append(_coerce(value, f.type))

    sql = f"select {', '.join(select_parts)}\nfrom {metric.base_table} as {_BASE_ALIAS}"
    for j in joins:
        sql += f"\n{j}"
    if where_parts:
        sql += "\nwhere " + " and ".join(where_parts)
    if group_dims:
        positions = ", ".join(str(i + 1) for i in range(len(group_dims)))
        sql += f"\ngroup by {positions}\norder by {positions}"

    return CompiledQuery(
        metric=metric_name,
        definition=metric.definition,
        unit=metric.unit,
        dimensions=group_dims,
        time_grain=grain,
        sql=sql,
        params=params,
    )
