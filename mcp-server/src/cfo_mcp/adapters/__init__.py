"""Warehouse adapters. `base` defines the interface; `duckdb` is the default
local read-only backend. A Snowflake/BigQuery backend can implement the same
interface without touching the server or the guards."""
