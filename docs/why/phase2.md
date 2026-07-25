# Why — Phase 2: Data contracts, the ingestion gate, and Bronze

Interview-defensible notes for the ingestion layer.

## "What is a data contract here, and why bother?"

A data contract is a machine-readable promise about a feed's shape: required
columns, types, nullability, and the domain of legal values (allowed values,
ranges, key patterns). It matters because a bad source file is the most common
way a warehouse gets silently corrupted. The contract is enforced *at the door*
by `load_to_bronze.py`, which refuses to land any file that fails — so
corruption is caught with a precise, per-column report instead of surfacing as a
weird number on the CFO's dashboard three layers later.

## "The data is full of duplicates and dirty regions — why doesn't the contract reject that?"

Because that dirtiness is **legal**, not corrupt. The whole point of the Silver
layer is to dedup, conform, and null-handle. If the gate rejected the everyday
mess, nothing would ever load. So the contract is a *structural* gate: it allows
the known messiness (POS `region` is just a non-null string; duplicates are
permitted; `customer_id` is nullable) but rejects genuine corruption — a missing
column, a currency of `GBP`, a date in 1999, a malformed key, a duplicate GL id.
The unit tests in `ingestion/tests/` prove both directions: dirty-but-legal data
passes; corrupt data is rejected. This distinction is the heart of the design.

> I found a real bug writing these: a contract that required `discount_amount >= 0`
> failed the batch, because a *return* (negative quantity) correctly produces a
> negative discount. The fix was to loosen the contract, not the data — a good
> illustration of the allow-legal / reject-corrupt line.

## "Why land Bronze as raw strings instead of typed columns?"

Because raw means raw. Casting is a transformation and can fail or silently
coerce; if I cast on landing and get it wrong, I've lost the source of truth. So
Bronze stores every column exactly as it arrived (as `STRING`) plus typed
ingestion metadata, and the *typing* happens one step later in the dbt bronze
view models — in version-controlled, testable SQL. If a downstream number looks
wrong, I can always replay from a byte-faithful Bronze and prove whether it was
the source or my logic.

## "How is ingestion idempotent? Bronze is append-only — won't re-running double it?"

`_batch_id` is the SHA-256 of the file's bytes. Before loading, the loader checks
whether that batch already exists in the target table and skips it if so. Same
bytes → same id → no-op. So `make bronze` is safe to re-run. This is independent
of the fact-table `merge` in Gold (Phase 4) — belt and braces at two layers.

## "Why the metadata columns?"

`_loaded_at`, `_source_file`, `_batch_id`, `_source_system` give lineage and
auditability: for any Bronze row I can say when it landed, which file and batch
it came from, and which system produced it. `_batch_id` doubles as the
idempotency key.

## Alternatives I rejected (and why)

| Choice | Rejected alternative | Why |
| ------ | -------------------- | --- |
| Custom pydantic validator | Great Expectations / Soda | Heavy for 5 feeds; the validator shares the same contract objects the loader types from; easier to read/test/explain |
| Structural gate (allow dirt) | Reject any anomaly | Rejecting legal messiness would block every load; cleaning is Silver's job |
| Raw-string Bronze | Type on landing | Casting is a transformation that can fail/coerce; raw landing stays replayable |
| Append-only + hash idempotency | Merge/upsert into Bronze | Bronze must be an immutable landing history; latest-wins belongs downstream |

See [ADR-0005](../decisions/0005-data-contracts-and-bronze-landing.md).
