"""Render the full data dictionary as markdown, for the ``schema://tables``
resource. The LLM reads this once to understand the whole warehouse: every
governed table, its columns, types, and business descriptions."""

from __future__ import annotations

from .adapters.base import WarehouseAdapter


def build_data_dictionary(adapter: WarehouseAdapter) -> str:
    lines: list[str] = [
        "# Finance Warehouse — Data Dictionary",
        "",
        "Read-only, governed tables in the `gold` (star schema) and `marts` "
        "(finance) schemas. All monetary measures are USD.",
        "",
    ]
    for t in adapter.list_tables():
        lines.append(f"## `{t.fqn}` — {t.row_count:,} rows")
        if t.description:
            lines.append("")
            lines.append(t.description)
        lines.append("")
        lines.append("| column | type | nullable | description |")
        lines.append("| --- | --- | --- | --- |")
        for c in adapter.get_columns(t):
            null = "yes" if c.nullable else "no"
            desc = (c.description or "").replace("|", "\\|")
            lines.append(f"| `{c.name}` | {c.data_type} | {null} | {desc} |")
        lines.append("")
    return "\n".join(lines)
