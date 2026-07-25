"""
Dagster orchestration: one scheduled pipeline that lands Bronze and then runs
the full dbt build (seeds, snapshots, models, and all tests).

Dependency wiring — the important bit:
The Python ingestion step must run BEFORE any dbt model that reads a raw source.
We achieve that the canonical dagster-dbt way: the ingestion `multi_asset`
*produces* the same asset keys that dbt assigns to its sources. dagster-dbt then
makes every source-reading model depend on the ingestion asset automatically:

    land_bronze (produces the 5 raw source assets)
        -> bronze_* views -> silver_* -> gold (+ snapshot) -> marts
        (+ dbt tests as asset checks throughout)

The pipeline runs against the DuckDB target (profiles.yml default) — local, no
cloud cost, same engine CI uses.
"""

import json
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetSpec,
    Definitions,
    MaterializeResult,
    ScheduleDefinition,
    define_asset_job,
    multi_asset,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv optional; env may already be exported
    load_dotenv = None

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = REPO_ROOT / "dbt_project"
DATA_RAW = REPO_ROOT / "data" / "raw"

# Load .env so DUCKDB_PATH / DBT_DUCKDB_SCHEMA resolve for the loader and dbt
# (harmless if missing — profiles.yml carries sane duckdb defaults).
if load_dotenv is not None:
    load_dotenv(REPO_ROOT / ".env")

# Represent the dbt project and (under `dagster dev`) prepare its manifest.
dbt_project = DbtProject(project_dir=DBT_DIR, profiles_dir=DBT_DIR, target="duckdb")
dbt_project.prepare_if_dev()

# Derive the exact asset keys dbt assigns to its raw sources, using the same
# default translator dbt_assets uses — so the ingestion asset produces precisely
# those keys and the DAG links up.
_translator = DagsterDbtTranslator()
_manifest = json.loads(Path(dbt_project.manifest_path).read_text(encoding="utf-8"))
SOURCE_KEYS = [_translator.get_asset_key(props) for props in _manifest["sources"].values()]


@multi_asset(
    specs=[AssetSpec(key, group_name="ingestion") for key in SOURCE_KEYS],
    compute_kind="python",
)
def land_bronze(context: AssetExecutionContext):
    """Validate each source file against its data contract and land it into the
    Bronze (raw) layer of DuckDB. Idempotent: content-hash batch ids mean a
    re-run skips already-loaded files rather than duplicating them. Produces the
    raw source assets that the dbt models depend on."""
    from ingestion.load_to_bronze import main as load_main

    exit_code = load_main(["--source-dir", str(DATA_RAW), "--target", "duckdb"])
    if exit_code != 0:
        raise Exception(f"Bronze landing failed with exit code {exit_code}")
    context.log.info("Bronze landing complete.")
    for key in SOURCE_KEYS:
        yield MaterializeResult(asset_key=key)


@dbt_assets(manifest=dbt_project.manifest_path)
def northwind_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """Every dbt node — seeds, snapshots, models — plus all data tests as asset
    checks, executed via a single `dbt build`."""
    yield from dbt.cli(["build"], context=context).stream()


# One job over everything, on a daily schedule.
northwind_job = define_asset_job("northwind_pipeline", selection="*")

daily_refresh = ScheduleDefinition(
    name="daily_northwind_refresh",
    job=northwind_job,
    cron_schedule="0 6 * * *",  # 06:00 every day
)

defs = Definitions(
    assets=[land_bronze, northwind_dbt_assets],
    jobs=[northwind_job],
    schedules=[daily_refresh],
    resources={
        "dbt": DbtCliResource(project_dir=str(DBT_DIR), profiles_dir=str(DBT_DIR), target="duckdb"),
    },
)
