# Northwind lakehouse — developer entrypoints.
#
# Every target runs through `uv`, so a fresh clone needs only `uv` installed.
# dbt is always invoked with explicit --project-dir/--profiles-dir so no target
# has to change directories (keeps recipes portable across cmd.exe and POSIX sh).
#
# Connection secrets come from environment variables (see .env.example). Export
# them in your shell before running dbt targets, e.g. on PowerShell:
#   Get-Content .env | Where-Object {$_ -notmatch '^#' -and $_ -match '='} | ForEach-Object { $p=$_.Split('=',2); [Environment]::SetEnvironmentVariable($p[0],$p[1]) }

# dbt >= 1.5 wants --project-dir/--profiles-dir AFTER the subcommand, so these
# are appended as flags rather than baked into the command prefix.
DBT = uv run dbt
DBT_FLAGS = --project-dir dbt_project --profiles-dir dbt_project

.PHONY: help setup data validate bronze bronze-dry pytest connection-test deps run build test docs lint fmt dagster clean

help:                 ## Show this help
	@echo Northwind lakehouse targets:
	@echo   make setup           - create venv, install all deps, install dbt packages
	@echo   make data            - generate the synthetic source CSVs into data/raw
	@echo   make connection-test - verify the BigQuery connection (dbt debug)
	@echo   make run             - dbt run (build all models, no tests)
	@echo   make build           - dbt build (models + tests + snapshots + seeds)
	@echo   make test            - dbt test (run all data tests)
	@echo   make docs            - generate and serve the dbt docs site
	@echo   make lint            - sqlfluff lint the models
	@echo   make fmt             - sqlfluff fix (auto-format) the models
	@echo   make dagster         - launch the Dagster UI locally
	@echo   make clean           - remove dbt target/, packages, generated data

setup:                ## Create the environment and install everything
	uv python install 3.11
	uv sync --extra platform --extra dev
	$(DBT) deps $(DBT_FLAGS)

deps:                 ## Install/refresh dbt packages only
	$(DBT) deps $(DBT_FLAGS)

data:                 ## Generate the reproducible synthetic dataset
	uv run python scripts/generate_synthetic_data.py

validate:             ## Validate every file in data/raw against its data contract
	uv run python -c "import glob,subprocess,sys; [subprocess.run([sys.executable,'-m','ingestion.validate','--file',f],check=False) for f in glob.glob('data/raw/*.csv')]"

bronze-dry:           ## Validate + show the Bronze load plan (no warehouse needed)
	uv run python -m ingestion.load_to_bronze --source-dir data/raw --dry-run

bronze:               ## Validate + land all source files into Bronze (append-only, idempotent)
	uv run python -m ingestion.load_to_bronze --source-dir data/raw

pytest:               ## Run the Python ingestion unit tests
	uv run pytest ingestion/tests -q

connection-test:      ## Confirm the warehouse connection is configured correctly
	$(DBT) debug $(DBT_FLAGS)

run:                  ## Build all models (no tests)
	$(DBT) run $(DBT_FLAGS)

build:                ## Build models + run tests + snapshots + seeds (the CI command)
	$(DBT) build $(DBT_FLAGS)

test:                 ## Run all data-quality tests
	$(DBT) test $(DBT_FLAGS)

docs:                 ## Generate and serve dbt documentation
	$(DBT) docs generate $(DBT_FLAGS)
	$(DBT) docs serve $(DBT_FLAGS)

lint:                 ## Lint SQL with sqlfluff
	uv run sqlfluff lint dbt_project/models

fmt:                  ## Auto-fix SQL formatting
	uv run sqlfluff fix dbt_project/models

dagster:              ## Launch the Dagster UI
	uv run dagster dev -m orchestration.definitions

clean:                ## Remove build artefacts and generated data
	$(DBT) clean
	uv run python -c "import shutil,glob,os; [os.remove(f) for f in glob.glob('data/raw/*.csv')]"
