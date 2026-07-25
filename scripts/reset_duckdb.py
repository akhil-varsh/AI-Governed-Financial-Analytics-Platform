"""Delete the local DuckDB database so a rebuild starts clean.

The snapshot history is bootstrapped by replaying the three dated extracts
(`make snapshots`); that replay must start from an EMPTY snapshot, so a full
deterministic local rebuild begins by removing the database file."""
import os

path = os.environ.get("DUCKDB_PATH", "northwind.duckdb")
for p in (path, path + ".wal"):
    if os.path.exists(p):
        os.remove(p)
        print(f"removed {p}")
    else:
        print(f"(not present) {p}")
