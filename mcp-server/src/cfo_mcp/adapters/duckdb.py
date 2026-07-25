"""DuckDB adapter — the default local backend.

The connection is opened ``read_only=True`` (Layer 1 of defense-in-depth): even
if every other guard failed, the engine itself would reject a write. Discovery
uses ``information_schema`` filtered to the allowlisted schemas, so nothing
outside ``gold``/``marts`` is ever visible. User-supplied table names are
resolved against that validated set — never concatenated blindly into SQL.
"""

from __future__ import annotations

import threading
from pathlib import Path

import duckdb

from ..catalog import describe
from .base import ColumnInfo, QueryResult, TableInfo, WarehouseAdapter

PREVIEW_MAX = 50
_SAMPLE_ROWS = 25      # rows scanned to derive per-column sample values
_SAMPLES_PER_COL = 3


class DuckDBAdapter(WarehouseAdapter):
    def __init__(self, path: str | Path, allowed_schemas: tuple[str, ...]):
        self._path = str(path)
        self._allowed = tuple(allowed_schemas)
        if not Path(self._path).exists():
            raise FileNotFoundError(
                f"Warehouse not found at {self._path}. Run `make export` (or "
                f"scripts/export_gold.py) to build it from the lakehouse first."
            )
        # read_only=True is Layer 1: the engine cannot write, full stop.
        self._con = duckdb.connect(self._path, read_only=True)
        self._tables_cache: list[TableInfo] | None = None
        self._index_cache: dict[str, TableInfo] | None = None
        self._has_meta = self._detect_meta()

    # --- discovery ---------------------------------------------------------- #
    def list_tables(self) -> list[TableInfo]:
        if self._tables_cache is not None:
            return self._tables_cache

        placeholders = ", ".join("?" for _ in self._allowed)
        rows = self._con.execute(
            f"""
            select table_schema, table_name
            from information_schema.tables
            where table_schema in ({placeholders})
            order by table_schema, table_name
            """,
            list(self._allowed),
        ).fetchall()

        out: list[TableInfo] = []
        for schema_name, table in rows:
            count = self._con.execute(
                f'select count(*) from "{schema_name}"."{table}"'
            ).fetchone()[0]
            out.append(
                TableInfo(
                    schema_name=schema_name,
                    name=table,
                    row_count=int(count),
                    description=self._table_description(schema_name, table),
                )
            )
        self._tables_cache = out
        return out

    def resolve_table(self, name: str) -> TableInfo | None:
        """Match a user string to a validated table. Accepts 'schema.table' or a
        bare 'table' (if unambiguous). Case-insensitive. No SQL is built from the
        raw input — we only ever return a TableInfo whose identifiers came from
        information_schema."""
        if self._index_cache is None:
            index: dict[str, TableInfo] = {}
            collisions: set[str] = set()
            for t in self.list_tables():
                index[t.fqn.lower()] = t
                bare = t.name.lower()
                if bare in index and index[bare] is not t:
                    collisions.add(bare)
                else:
                    index[bare] = t
            for bare in collisions:      # ambiguous bare names must be qualified
                index.pop(bare, None)
            self._index_cache = index
        return self._index_cache.get((name or "").strip().lower())

    # --- schema + preview --------------------------------------------------- #
    def get_columns(self, table: TableInfo) -> list[ColumnInfo]:
        cols = self._con.execute(
            """
            select column_name, data_type, is_nullable
            from information_schema.columns
            where table_schema = ? and table_name = ?
            order by ordinal_position
            """,
            [table.schema_name, table.name],
        ).fetchall()

        descriptions = self._column_descriptions(table)
        samples = self._sample_values(table)

        return [
            ColumnInfo(
                name=name,
                data_type=data_type,
                nullable=(str(is_nullable).upper() == "YES"),
                description=descriptions.get(name, ""),
                sample_values=samples.get(name, []),
            )
            for name, data_type, is_nullable in cols
        ]

    def preview(self, table: TableInfo, n: int) -> QueryResult:
        n = max(1, min(int(n), PREVIEW_MAX))          # clamp regardless of caller
        cur = self._con.execute(f'select * from "{table.schema_name}"."{table.name}" limit {n}')
        columns = [d[0] for d in cur.description]
        return QueryResult(columns=columns, rows=cur.fetchall())

    def execute(self, sql: str, timeout_s: float, params: list | None = None) -> QueryResult:
        # Hard timeout via DuckDB's cross-thread interrupt(): a watchdog timer
        # cancels the running query if it overruns. This is the last-resort
        # protection against an accidental (or deliberate) runaway query.
        timer = threading.Timer(timeout_s, self._con.interrupt)
        timer.start()
        try:
            cur = self._con.execute(sql, params) if params else self._con.execute(sql)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
        except duckdb.InterruptException as exc:  # watchdog fired
            raise TimeoutError(f"query exceeded {timeout_s:.1f}s timeout") from exc
        finally:
            timer.cancel()
        return QueryResult(columns=columns, rows=rows)

    def explain(self, sql: str) -> str:
        # Plain EXPLAIN — plans the query, does NOT execute it (no ANALYZE).
        rows = self._con.execute(f"explain {sql}").fetchall()
        return "\n".join(str(r[-1]) for r in rows)

    def close(self) -> None:
        self._con.close()

    # --- internals ---------------------------------------------------------- #
    def _detect_meta(self) -> bool:
        row = self._con.execute(
            "select count(*) from information_schema.tables "
            "where table_schema = 'meta' and table_name = 'column_docs'"
        ).fetchone()
        return bool(row and row[0])

    def _table_description(self, schema_name: str, table: str) -> str:
        if self._has_meta:
            row = self._con.execute(
                "select description from meta.table_docs where table_schema = ? and table_name = ?",
                [schema_name, table],
            ).fetchone()
            if row and row[0]:
                return row[0]
        return describe(schema_name, table)  # fallback to the hand-curated one-liners

    def _column_descriptions(self, table: TableInfo) -> dict[str, str]:
        if not self._has_meta:
            return {}
        rows = self._con.execute(
            "select column_name, description from meta.column_docs "
            "where table_schema = ? and table_name = ?",
            [table.schema_name, table.name],
        ).fetchall()
        return {c: (d or "") for c, d in rows}

    def _sample_values(self, table: TableInfo) -> dict[str, list[str]]:
        cur = self._con.execute(
            f'select * from "{table.schema_name}"."{table.name}" limit {_SAMPLE_ROWS}'
        )
        colnames = [d[0] for d in cur.description]
        acc: dict[str, list[str]] = {c: [] for c in colnames}
        for row in cur.fetchall():
            for c, v in zip(colnames, row):
                if v is None:
                    continue
                s = str(v)
                if len(acc[c]) < _SAMPLES_PER_COL and s not in acc[c]:
                    acc[c].append(s)
        return acc
