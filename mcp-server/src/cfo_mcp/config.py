"""Runtime configuration.

Kept tiny and explicit. The two governance-critical settings are
``allowed_schemas`` (the ONLY schemas any tool may reach — Layer 3 of the
defense-in-depth model) and the read-only warehouse path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent          # src/cfo_mcp
PROJECT_ROOT = PACKAGE_ROOT.parent.parent               # mcp-server/


@dataclass(frozen=True)
class Settings:
    # Read-only DuckDB file holding the exported Gold + marts tables.
    warehouse_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("CFO_WAREHOUSE_PATH", PROJECT_ROOT / "data" / "warehouse.duckdb")
        )
    )
    # Schema allowlist — nothing outside these is discoverable or queryable.
    allowed_schemas: tuple[str, ...] = ("gold", "marts")
    # Hard cap on rows any query may return.
    max_rows: int = 1000
    # Statement timeout for the raw-SQL escape hatch (seconds).
    query_timeout_s: float = 10.0
    # Semantic-layer metric catalogue.
    metrics_path: Path = field(default_factory=lambda: PACKAGE_ROOT / "semantic" / "metrics.yaml")
    # Structured audit log (JSON lines). Also mirrored to stderr.
    audit_log_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("CFO_AUDIT_LOG", PROJECT_ROOT / "logs" / "audit.log")
        )
    )


settings = Settings()
