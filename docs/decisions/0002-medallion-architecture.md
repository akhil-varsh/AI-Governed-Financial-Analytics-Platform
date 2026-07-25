# ADR-0002: Medallion (Bronze / Silver / Gold) architecture

- **Status:** Accepted
- **Date:** 2026-07-24

## Context

Northwind's data arrives as messy, disconnected CSV extracts from three source
systems. Stakeholders need a clean star schema and finance marts. We need a
layering scheme that separates "land it faithfully" from "clean it" from "model
it for consumption", so failures are isolated and each concern is testable.

## Decision

Adopt a strict **medallion architecture**:

- **Bronze** — raw landed data, append-only, with ingestion metadata
  (`_loaded_at`, `_source_file`, `_batch_id`). No transformation. This preserves
  an immutable audit trail: we can always reprocess history from Bronze without
  re-pulling from the source.
- **Silver** — cleaned, typed, deduplicated, conformed. Business keys resolved,
  nulls handled explicitly, currencies converted. One row per business entity
  per grain.
- **Gold** — dimensional star schema (facts + conformed dimensions, incl. SCD2)
  for consumption.
- **Marts** — business-facing finance models on top of Gold.

Each layer is its own BigQuery dataset for browsability and access control.

## Consequences

- Clear separation of concerns; each layer independently testable.
- Bronze immutability enables full reprocessing and debugging ("was it the
  source or our logic?").
- More models/objects than a flatter design — accepted for governance and
  clarity.

## Alternatives considered

- **One Big Table (OBT) / flat wide model straight from sources** — rejected:
  fast to demo but couples ingestion, cleaning, and modelling into one
  untestable step; no audit layer; painful to evolve. We still expose
  consumption-friendly wide models, but in the Marts layer, built *on* a
  governed star schema.
- **Two layers (raw + presentation)** — rejected: conflates cleaning and
  dimensional modelling, which have different change cadences and owners.
- **Star schema in Silver directly** — rejected: mixing conformance with
  dimensional design makes it hard to reuse conformed entities across multiple
  downstream models.
