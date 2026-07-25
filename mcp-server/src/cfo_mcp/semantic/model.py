"""Semantic-layer schema + loader.

Metrics, dimensions, and filters are declared in ``metrics.yaml`` and parsed into
these validated models. Validation runs at load time, so an authoring mistake
(a metric that allows a dimension we didn't define, a base table outside the
allowlist, a bad default time grain) fails fast and loudly rather than producing
wrong SQL later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

# Time grains map to the fiscal dimensions grouped by. Grouping by quarter/month
# always includes fiscal_year so the buckets are unambiguous across years.
TIME_GRAINS: dict[str, list[str]] = {
    "none": [],
    "fiscal_year": ["fiscal_year"],
    "fiscal_quarter": ["fiscal_year", "fiscal_quarter"],
    "fiscal_month": ["fiscal_year", "fiscal_month"],
}

ALLOWED_BASE_SCHEMAS = ("gold", "marts")

FilterType = Literal["string", "int", "number", "bool", "date"]


class SemanticError(Exception):
    """Raised when a query_metric request is invalid. The message is the denial
    reason surfaced to the caller."""


class Dimension(BaseModel):
    sql: str                       # SQL expression selecting the dimension value
    join: str | None = None        # join needed to reach it ({base} = fact alias)
    description: str = ""
    groupable: bool = True         # False = usable only in required_joins (e.g. customer)


class FilterDef(BaseModel):
    sql: str
    join: str | None = None
    type: FilterType = "string"
    description: str = ""


class Metric(BaseModel):
    label: str
    definition: str
    base_table: str
    expression: str                # the aggregate, e.g. "sum(net_revenue)"
    unit: str = ""                  # "usd", "pct", "count", ...
    base_filter: str | None = None  # a static, authored WHERE always applied
    allowed_dimensions: list[str] = []
    allowed_filters: list[str] = []
    required_joins: list[str] = []  # dimension keys whose joins are always added
    default_time_grain: str = "none"
    owner: str = "Finance Data Team"


class SemanticLayer(BaseModel):
    dimensions: dict[str, Dimension]
    filters: dict[str, FilterDef]
    metrics: dict[str, Metric]

    @model_validator(mode="after")
    def _validate_references(self) -> "SemanticLayer":
        for name, metric in self.metrics.items():
            schema = metric.base_table.split(".")[0]
            if schema not in ALLOWED_BASE_SCHEMAS:
                raise ValueError(f"metric '{name}': base_table '{metric.base_table}' is outside {ALLOWED_BASE_SCHEMAS}")
            if metric.default_time_grain not in TIME_GRAINS:
                raise ValueError(f"metric '{name}': bad default_time_grain '{metric.default_time_grain}'")
            for dim in metric.allowed_dimensions:
                if dim not in self.dimensions:
                    raise ValueError(f"metric '{name}': unknown dimension '{dim}'")
            for key in metric.required_joins:
                if key not in self.dimensions:
                    raise ValueError(f"metric '{name}': unknown required_join dimension '{key}'")
            for flt in metric.allowed_filters:
                if flt not in self.filters:
                    raise ValueError(f"metric '{name}': unknown filter '{flt}'")
        return self


def load_semantic_layer(path: str | Path) -> SemanticLayer:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return SemanticLayer(**data)
