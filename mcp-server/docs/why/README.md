# Per-phase "why" notes

Interview-style write-ups of each phase's key decisions and the rejected
alternatives — less formal than the [ADRs](../decisions/README.md).

| Phase | Note | Covers |
| --- | --- | --- |
| 1 | [phase1.md](phase1.md) | Scaffold, read-only adapter, official FastMCP, protocol annotations |
| 2 | [phase2.md](phase2.md) | Schema/preview tools; identifier safety by resolution; dbt-sourced descriptions |
| 3 | [phase3.md](phase3.md) | The guards, adversarial-tests-first; per-layer stop/gap analysis |
| 4 | [phase4.md](phase4.md) | `execute_sql`/`explain_query`; why a guarded escape hatch; EXPLAIN not ANALYZE |
| 5 | [phase5.md](phase5.md) | The semantic layer; safety by construction; correctness encoded once |
| 6 | [phase6.md](phase6.md) | Audit layer; stderr-not-stdout; log arguments even on denial |
