"""Render the metric catalogue as markdown, for the ``metrics://catalogue``
resource. The LLM reads this to learn which governed metrics exist and how each
may be sliced/filtered — so it calls query_metric instead of writing SQL."""

from __future__ import annotations

from .model import SemanticLayer


def build_catalogue(layer: SemanticLayer) -> str:
    lines: list[str] = [
        "# Metric Catalogue (semantic layer)",
        "",
        "Ask for these **metrics** by name with `query_metric` — do not write the "
        "formulas yourself. Each metric owns its definition, so a number means the "
        "same thing everywhere.",
        "",
    ]
    for name, m in layer.metrics.items():
        lines.append(f"## `{name}` — {m.label}")
        lines.append("")
        lines.append(m.definition)
        lines.append("")
        lines.append(f"- **base table:** `{m.base_table}`")
        lines.append(f"- **unit:** {m.unit or 'n/a'}")
        lines.append(f"- **default time grain:** {m.default_time_grain}")
        lines.append(f"- **dimensions:** {', '.join(m.allowed_dimensions) or 'none'}")
        lines.append(f"- **filters:** {', '.join(m.allowed_filters) or 'none'}")
        lines.append(f"- **owner:** {m.owner}")
        lines.append("")
    return "\n".join(lines)
