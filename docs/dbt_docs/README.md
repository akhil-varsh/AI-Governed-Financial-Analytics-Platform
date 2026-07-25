# dbt documentation site (generated snapshot)

This folder is a **committed static snapshot** of the dbt docs site — the full
model/column catalog, lineage graph (DAG), tests, and descriptions.

## Viewing it

Open `index.html` in a browser. It reads `manifest.json` and `catalog.json` from
this same folder, so keep the three files together. (Some browsers block local
`fetch`; if the page looks empty, serve the folder instead:
`python -m http.server` from here, or run `make docs` from the repo root for the
live dbt server.)

## Regenerating

From the repo root, with your environment loaded:

```
make docs-static
```

which runs `dbt docs generate` and copies the fresh `index.html`,
`manifest.json`, and `catalog.json` here.

## What it proves

- Every model and every column has a description (verified: **0 blank
  descriptions** across 20 models + 5 sources).
- Full lineage from the `raw` sources through Bronze → Silver → Gold → marts.
- All data tests (source, model, and singular business tests) attached to their
  models.
