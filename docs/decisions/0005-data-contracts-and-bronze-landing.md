# ADR-0005: Data contracts as an ingestion gate, and raw Bronze landing

- **Status:** Accepted
- **Date:** 2026-07-25

## Context

Bad source files are the single most common way a warehouse gets silently
corrupted. We want to stop a malformed extract *before* it reaches Bronze, while
still accepting the everyday messiness (duplicates, inconsistent spellings, null
ids, returns, mixed currency) that the Silver layer is specifically built to
clean. We also need Bronze itself to be a faithful, reprocessable record.

## Decision

1. **A YAML data contract per feed** (`ingestion/contracts/*.yml`) declares
   required columns, logical types, nullability, and value domains (allowed
   values, ranges, key formats). Contracts are parsed and validated by a pydantic
   model (`ingestion/contracts.py`), so a malformed contract fails fast too.

2. **The contract is a structural gate, not a cleaner.** It rejects genuine
   corruption (missing column, out-of-domain currency, out-of-range date, bad key
   format, non-unique key where required) but *deliberately allows* the injected
   dirtiness — e.g. POS `region` is contracted only as a non-null string, POS
   duplicates are permitted, `customer_id` is nullable. Each looseness is
   commented in the YAML and covered by a test in `ingestion/tests/`.

3. **Validation is a hard gate in the loader.** `load_to_bronze.py` validates
   each file and refuses to land a failing one (`raise`, non-zero exit).

4. **Bronze lands raw.** Every source column is stored as `STRING` exactly as it
   arrived, plus typed ingestion metadata (`_loaded_at`, `_source_file`,
   `_batch_id`, `_source_system`). Typing happens one step later, in the dbt
   bronze *view* models, so the physical landing is byte-faithful and history is
   always reprocessable.

5. **Append-only + idempotent.** Loads are `WRITE_APPEND`. `_batch_id` is the
   SHA-256 of the file's bytes; the loader skips a batch already present, so
   re-running the loader can never double-load.

## Consequences

- A corrupt file is caught at the door with a precise, per-rule report.
- Bronze is an immutable, replayable audit layer.
- Ingestion is safely re-runnable (idempotent), independent of the downstream
  fact-table merge.
- Contracts are lightweight to author and live next to the code they govern.

## Alternatives considered

- **Great Expectations / Soda** instead of a custom pydantic validator —
  powerful, but heavy for five feeds, adds a large dependency and its own DSL,
  and the "expectations" would still need the same allow-the-dirt tuning. A
  ~250-line validator is easier to read, test, and explain, and shares the exact
  same contract objects the loader uses for typing. Revisit if feed count or
  team size grows.
- **Type Bronze on landing** (cast to NUMERIC/DATE at load) — rejected: casting
  is a transformation and can itself fail or coerce silently; keeping Bronze as
  raw strings preserves the source faithfully and moves all typing into
  version-controlled dbt SQL where it's testable.
- **Upsert/merge into Bronze** instead of append-only — rejected: Bronze is meant
  to be an immutable landing history; dedup/latest-wins belongs in Silver/Gold.
- **Schema-on-read only (no gate)** — rejected: lets a corrupt file poison the
  warehouse and pushes the failure far downstream where it's expensive to trace.
