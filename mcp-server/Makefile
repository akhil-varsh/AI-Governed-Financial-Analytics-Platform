# CFO MCP server — developer entrypoints. Everything runs through uv.
.PHONY: help setup export test run inspect demo audit clean

help:                 ## Show targets
	@echo   make setup    - create venv + install deps (incl. dev)
	@echo   make export   - build data/warehouse.duckdb from the lakehouse Gold/marts
	@echo   make test     - run the pytest suite
	@echo   make run      - run the MCP server over stdio (as Claude Desktop would)
	@echo   make inspect  - launch the MCP Inspector UI against the server
	@echo   make clean    - remove the exported warehouse

setup:                ## Install everything
	uv sync --extra dev

export:               ## Export Gold + marts into the read-only warehouse
	uv run python scripts/export_gold.py

test:                 ## Run tests
	uv run pytest tests -q

run:                  ## Launch the server over stdio
	uv run cfo-mcp

inspect:              ## Interactive MCP Inspector (browser UI) for manual tool testing
	uv run mcp dev src/cfo_mcp/server.py

demo:                 ## Replay the scripted CFO demo conversation (for a GIF)
	uv run python scripts/demo.py

audit:                ## Summarise the audit log
	uv run python scripts/analyze_audit.py

clean:                ## Remove the exported warehouse
	uv run python -c "import os,glob; [os.remove(f) for f in glob.glob('data/*.duckdb*')]"
