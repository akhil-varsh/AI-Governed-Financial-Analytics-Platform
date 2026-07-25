"""
Land validated source files into the Bronze (raw) layer in BigQuery.

Pipeline per file:
    discover (by contract glob)  ->  VALIDATE (gate)  ->  land to Bronze

Design choices
--------------
* RAW means raw. Bronze tables store every source column exactly as it arrived
  (as STRING), plus typed ingestion metadata. No casting, no dedup, no
  conforming — that is Silver's job. The dbt bronze *view* models apply typing
  as a thin pass-through; the physical landing here stays byte-faithful so we can
  always reprocess history and answer "was it the source or our logic?".

* APPEND-ONLY. Every load is WRITE_APPEND; history is never mutated.

* IDEMPOTENT INGESTION. A `_batch_id` is the SHA-256 of the file's bytes. Before
  loading, we check whether that batch_id already exists in the target table and
  skip if so. Re-running `load_to_bronze` on the same drop folder is therefore a
  no-op — it cannot double-load. (Downstream, the fact tables also merge on a
  unique key; the two mechanisms are independent belt-and-braces.)

* VALIDATION IS A HARD GATE. A file that fails its contract is never landed; the
  loader raises and reports, so a bad file cannot poison Bronze.

Requires the same env vars as dbt (see .env.example): DBT_BIGQUERY_PROJECT,
DBT_BIGQUERY_KEYFILE, DBT_BIGQUERY_DATASET. Bronze lands in
`<DBT_BIGQUERY_DATASET>_raw`, which the dbt source `raw` points at.

    python -m ingestion.load_to_bronze --source-dir data/raw            # load everything
    python -m ingestion.load_to_bronze --source-dir data/raw --dry-run  # validate + plan only
    python -m ingestion.load_to_bronze --source-dir data/raw --feed pos_orders
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import pandas as pd

from ingestion.contracts import FeedContract, load_all_contracts
from ingestion.validate import validate_file

# Metadata columns stamped on every Bronze row. Kept minimal and prefixed with
# underscore so they never collide with a source column.
META_LOADED_AT = "_loaded_at"
META_SOURCE_FILE = "_source_file"
META_BATCH_ID = "_batch_id"
META_SOURCE_SYSTEM = "_source_system"


def batch_id_for(path: Path) -> str:
    """Content hash of the file -> stable batch id. Identical bytes => identical
    id => idempotent re-load."""
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return h[:16]


def discover(source_dir: Path, contract: FeedContract) -> list[Path]:
    return sorted(source_dir.glob(contract.file_glob))


def raw_dataset(target: str = "duckdb") -> str:
    """The Bronze landing schema/dataset, `<base>_raw`. The base matches whatever
    schema the corresponding dbt target uses, so the dbt `raw` source lines up."""
    base_env = "DBT_DUCKDB_SCHEMA" if target == "duckdb" else "DBT_BIGQUERY_DATASET"
    return f"{os.environ.get(base_env, 'northwind_dev')}_raw"


def prepare_frame(path: Path, contract: FeedContract) -> pd.DataFrame:
    """Read raw (all string) and stamp ingestion metadata."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)  # keep '' as '' — no NA inference in Bronze
    # tz-aware datetime so it maps cleanly to a BigQuery TIMESTAMP column.
    df[META_LOADED_AT] = pd.Timestamp.now(tz="UTC")
    df[META_SOURCE_FILE] = path.name
    df[META_BATCH_ID] = batch_id_for(path)
    df[META_SOURCE_SYSTEM] = contract.source_system
    return df


# --------------------------------------------------------------------------- #
# BigQuery side (imported lazily so --dry-run needs no credentials)
# --------------------------------------------------------------------------- #
def _bq_client():
    from google.cloud import bigquery  # lazy

    project = os.environ["DBT_BIGQUERY_PROJECT"]
    keyfile = os.environ.get("DBT_BIGQUERY_KEYFILE")
    if keyfile:
        return bigquery.Client.from_service_account_json(keyfile, project=project)
    return bigquery.Client(project=project)  # falls back to ADC / gcloud oauth


def _bq_schema(df: pd.DataFrame):
    from google.cloud import bigquery

    fields = []
    for col in df.columns:
        if col == META_LOADED_AT:
            fields.append(bigquery.SchemaField(col, "TIMESTAMP"))
        else:  # every source column + the other metadata cols land as STRING
            fields.append(bigquery.SchemaField(col, "STRING"))
    return fields


def _batch_already_loaded(client, table_fqn: str, batch_id: str) -> bool:
    from google.cloud import bigquery
    from google.api_core.exceptions import NotFound

    try:
        client.get_table(table_fqn)
    except NotFound:
        return False
    query = f"SELECT COUNT(1) AS n FROM `{table_fqn}` WHERE {META_BATCH_ID} = @b"
    job = client.query(query, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("b", "STRING", batch_id)]))
    return next(iter(job.result())).n > 0


def land_to_bigquery(df: pd.DataFrame, contract: FeedContract, batch_id: str) -> str:
    from google.cloud import bigquery

    client = _bq_client()
    dataset = raw_dataset("bigquery")
    client.create_dataset(bigquery.Dataset(f"{client.project}.{dataset}"), exists_ok=True)
    table_fqn = f"{client.project}.{dataset}.{contract.bronze_table}"

    if _batch_already_loaded(client, table_fqn, batch_id):
        return f"skip (batch {batch_id} already loaded)"

    job_config = bigquery.LoadJobConfig(
        schema=_bq_schema(df),
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    client.load_table_from_dataframe(df, table_fqn, job_config=job_config).result()
    return f"appended {len(df):,} rows -> {table_fqn}"


# --------------------------------------------------------------------------- #
# DuckDB side (local execution target — no cloud, no DML restriction)
# --------------------------------------------------------------------------- #
def land_to_duckdb(df: pd.DataFrame, contract: FeedContract, batch_id: str) -> str:
    import duckdb  # lazy

    schema = raw_dataset("duckdb")
    table = contract.bronze_table
    con = duckdb.connect(os.environ.get("DUCKDB_PATH", "northwind.duckdb"))
    try:
        con.execute(f'create schema if not exists "{schema}"')
        fqn = f'"{schema}"."{table}"'
        exists = con.execute(
            "select count(*) from information_schema.tables where table_schema = ? and table_name = ?",
            [schema, table]).fetchone()[0]
        if exists:
            already = con.execute(
                f'select count(*) from {fqn} where {META_BATCH_ID} = ?', [batch_id]).fetchone()[0]
            if already:
                return f"skip (batch {batch_id} already loaded)"

        con.register("df_v", df)
        if exists:
            con.execute(f"insert into {fqn} select * from df_v")
        else:
            con.execute(f"create table {fqn} as select * from df_v")
        return f"appended {len(df):,} rows -> {schema}.{table} (duckdb)"
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def load_feed(source_dir: Path, contract: FeedContract, dry_run: bool, target: str) -> list[str]:
    messages = []
    files = discover(source_dir, contract)
    if not files:
        return [f"{contract.feed}: no files matching {contract.file_glob!r}"]

    landers = {"bigquery": land_to_bigquery, "duckdb": land_to_duckdb}
    for path in files:
        # 1. HARD GATE — validate before anything touches Bronze.
        result = validate_file(path, contract)
        if not result.ok:
            raise ValueError(
                f"REJECTED {path.name}: file failed its contract, not landed.\n{result.report()}")

        df = prepare_frame(path, contract)
        bid = df[META_BATCH_ID].iloc[0]

        if dry_run:
            messages.append(
                f"{contract.feed}: OK {path.name} rows={len(df):,} batch={bid} "
                f"-> would append to {raw_dataset(target)}.{contract.bronze_table} ({target})")
        else:
            messages.append(f"{contract.feed}: {landers[target](df, contract, bid)}")
    return messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and land source files into Bronze.")
    parser.add_argument("--source-dir", default="data/raw", help="Folder containing dropped source files.")
    parser.add_argument("--feed", help="Only process this feed (default: all).")
    parser.add_argument("--target", default=os.environ.get("BRONZE_TARGET", "duckdb"),
                        choices=["duckdb", "bigquery"],
                        help="Where to land Bronze (default: duckdb, the local execution engine).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and print the load plan without connecting to the warehouse.")
    args = parser.parse_args(argv)

    source_dir = Path(args.source_dir)
    contracts = load_all_contracts()
    if args.feed:
        if args.feed not in contracts:
            print(f"Unknown feed {args.feed!r}. Known: {sorted(contracts)}", file=sys.stderr)
            return 2
        contracts = {args.feed: contracts[args.feed]}

    print(f"{'DRY RUN — ' if args.dry_run else ''}landing {len(contracts)} feed(s) "
          f"from {source_dir} into target '{args.target}'")
    print("-" * 68)
    exit_code = 0
    for contract in contracts.values():
        try:
            for msg in load_feed(source_dir, contract, args.dry_run, args.target):
                print(f"  {msg}")
        except ValueError as exc:
            print(f"  {exc}", file=sys.stderr)
            exit_code = 1  # a rejected file fails the whole run
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
