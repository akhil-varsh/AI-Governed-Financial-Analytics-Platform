# Per-phase "why" notes

Interview-style write-ups: the key design decisions of each phase, phrased as
questions you might be asked, with the rejected alternatives. Less formal than the
[ADRs](../decisions/README.md), and organised by build phase.

| Phase | Note | Covers |
| --- | --- | --- |
| 1 | [phase1.md](phase1.md) | Synthetic data, fiscal year, medallion, uv, portable SQL, secrets |
| 2 | [phase2.md](phase2.md) | Data contracts as a structural gate; raw Bronze; idempotent ingestion |
| 3 | [phase3.md](phase3.md) | Dedup, region conformance, null-key resolution, FX; the tie-out |
| 4 | [phase4.md](phase4.md) | Both SCD2 approaches, point-in-time joins, incremental merge, star vs OBT |
| 5 | [phase5.md](phase5.md) | Finance marts; the exact vs approximate bridge identity; as-was margin |
| 6 | [phase6.md](phase6.md) | Three-tier testing; tolerance-based tie-out; verified docs |
| 7 | [phase7.md](phase7.md) | Dagster asset wiring; DuckDB CI; the cautious-selection bug |
