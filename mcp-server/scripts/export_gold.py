"""Export the lakehouse Gold + marts tables into the MCP server's read-only
warehouse (`data/warehouse.duckdb`), plus a `meta` schema of column/table
descriptions pulled from the lakehouse dbt manifest.

This decouples the MCP server from the lakehouse build: the server ships its own
self-contained DuckDB file, reproducible with one command. Source schemas
(`northwind_dev_gold`/`_marts`) are renamed to the clean, allowlisted
`gold`/`marts`. Column descriptions come straight from dbt (DRY — they already
live in the lakehouse YAML), so the data dictionary is authentic, not re-typed.

The `meta` schema is intentionally NOT allowlisted, so it is never queryable
through the server — the adapter reads it only to annotate schemas.

    python scripts/export_gold.py
    NORTHWIND_DUCKDB=/path/to/northwind.duckdb python scripts/export_gold.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]   # .../northwind-lakehouse/mcp-server
LAKEHOUSE = PROJECT_ROOT.parent                       # .../northwind-lakehouse (this repo's root)
SRC = Path(os.environ.get("NORTHWIND_DUCKDB", LAKEHOUSE / "northwind.duckdb"))
DST = PROJECT_ROOT / "data" / "warehouse.duckdb"

SCHEMA_MAP = {"northwind_dev_gold": "gold", "northwind_dev_marts": "marts"}

# dbt manifest holds every model + column description. Prefer the fresh build
# artifact, fall back to the committed docs snapshot.
MANIFEST_CANDIDATES = [
    LAKEHOUSE / "dbt_project" / "target" / "manifest.json",
    LAKEHOUSE / "docs" / "dbt_docs" / "manifest.json",
]


def load_model_docs() -> dict[str, dict]:
    """Map dbt model name -> {'desc': str, 'cols': {col: desc}}."""
    for path in MANIFEST_CANDIDATES:
        if path.exists():
            manifest = json.loads(path.read_text(encoding="utf-8"))
            docs: dict[str, dict] = {}
            for node in manifest.get("nodes", {}).values():
                if node.get("resource_type") != "model":
                    continue
                docs[node["name"]] = {
                    "desc": (node.get("description") or "").strip(),
                    "cols": {
                        c: (col.get("description") or "").strip()
                        for c, col in node.get("columns", {}).items()
                    },
                }
            print(f"  loaded descriptions from {path.relative_to(LAKEHOUSE)}")
            return docs
    print("  (no dbt manifest found — descriptions will be blank)")
    return {}


def populate_meta(con: duckdb.DuckDBPyConnection, exported: list[tuple[str, str]],
                  model_docs: dict[str, dict]) -> None:
    con.execute("create schema if not exists meta")
    con.execute(
        "create or replace table meta.table_docs "
        "(table_schema varchar, table_name varchar, description varchar)"
    )
    con.execute(
        "create or replace table meta.column_docs "
        "(table_schema varchar, table_name varchar, column_name varchar, description varchar)"
    )
    for dst_schema, table in exported:
        md = model_docs.get(table, {})
        con.execute(
            "insert into meta.table_docs values (?, ?, ?)",
            [dst_schema, table, md.get("desc", "")],
        )
        cols = con.execute(
            "select column_name from information_schema.columns "
            "where table_schema = ? and table_name = ? order by ordinal_position",
            [dst_schema, table],
        ).fetchall()
        col_docs = md.get("cols", {})
        for (col,) in cols:
            con.execute(
                "insert into meta.column_docs values (?, ?, ?, ?)",
                [dst_schema, table, col, col_docs.get(col, "")],
            )


def main() -> None:
    if not SRC.exists():
        raise SystemExit(
            f"Source warehouse not found: {SRC}\n"
            f"Build the lakehouse first (its `make rebuild`), or set NORTHWIND_DUCKDB."
        )

    DST.parent.mkdir(parents=True, exist_ok=True)
    for leftover in (DST, DST.with_suffix(".duckdb.wal")):
        if leftover.exists():
            leftover.unlink()

    model_docs = load_model_docs()

    con = duckdb.connect(str(DST))
    con.execute(f"attach '{SRC}' as src (read_only)")
    exported: list[tuple[str, str]] = []
    try:
        for src_schema, dst_schema in SCHEMA_MAP.items():
            con.execute(f"create schema if not exists {dst_schema}")
            tables = con.execute(
                """
                select table_name from information_schema.tables
                where table_catalog = 'src' and table_schema = ?
                order by table_name
                """,
                [src_schema],
            ).fetchall()
            for (table,) in tables:
                con.execute(
                    f'create or replace table {dst_schema}."{table}" as '
                    f'select * from src.{src_schema}."{table}"'
                )
                n = con.execute(f'select count(*) from {dst_schema}."{table}"').fetchone()[0]
                print(f"  exported {dst_schema}.{table:<28} {n:>8,} rows")
                exported.append((dst_schema, table))

        populate_meta(con, exported, model_docs)
    finally:
        con.execute("detach src")
        con.close()

    print(f"\nExported {len(exported)} tables (+ meta descriptions) -> {DST}")


if __name__ == "__main__":
    main()
