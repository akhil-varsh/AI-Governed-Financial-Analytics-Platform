# Why — Phase 1: Scaffold, environment, and synthetic data

Written so you can defend these choices in an interview. Each section is a
question you might be asked, with the answer.

## "Why generate synthetic data instead of using a public dataset?"

Three reasons. **Reproducibility** — a seeded generator means anyone who clones
the repo gets byte-identical data with `make data`; a Kaggle link rots and can't
be regenerated. **Control** — I can inject *exactly* the data-quality problems I
want the Silver layer to demonstrate (duplicates, dirty regions, nulls, returns,
multi-currency, SCD2 changes), each one deterministic and documented. **Realism
where it counts** — the GL is posted *from* the sales facts, so the ledger
reconciles to revenue by construction, which lets me write a genuine
finance-style tie-out test instead of hand-waving.

## "Why does the fiscal year start in February?"

Because the brief says Northwind's does, and it's the single most common way
students get date logic wrong. Many retailers run non-calendar fiscal years
(Northwind: Feb–Jan). Baking `fiscal_year_start_month = 2` into `dbt_project.yml`
vars now means `dim_date` and every "by fiscal month" mart derive periods
correctly and in one place, rather than sprinkling `+ INTERVAL 1 MONTH` hacks
across models.

## "Why the medallion split, and why a separate dataset per layer?"

Separation of concerns and auditability — see ADR-0002. Bronze is an immutable,
append-only landing zone with ingestion metadata, so I can always answer "was
the bug in the source or in my transformation?" by replaying from Bronze.
Per-layer datasets (`_bronze`/`_silver`/`_gold`/`_marts`) make the warehouse
browsable by layer and let us grant stakeholders read access to `marts` only.

## "Why `uv` and a pinned lockfile?"

Reproducibility is a hard requirement (ADR-0004). This machine's default Python
is 3.14, which dbt-bigquery and Dagster don't support yet, so I pin 3.11 with
`uv python install 3.11` + `.python-version` — `uv` manages the interpreter *and*
the lockfile, which Poetry alone does not. `uv.lock` is committed so CI restores
the exact graph.

## "Why keep the SQL portable if you're committing to BigQuery?"

Because the firm's next portfolio company might be on Snowflake, and a migration
should be a small diff, not a rewrite (ADR-0003). All model SQL is ANSI; every
vendor function lives behind a macro in
`macros/warehouse_portability.sql`. The rule is greppable: if `SAFE_CAST` or a
backtick shows up in a model, it's a bug.

## "Why is the connection profile in the repo? Isn't that a security risk?"

The *profile* is in the repo; the *secrets* are not. `profiles.yml` reads every
sensitive value through `env_var()`, which fails loudly if the variable is
missing. `.env` (real values) is git-ignored; only `.env.example` (placeholders)
is committed. This gives a one-step onboarding without ever committing a key.

## Alternatives I explicitly rejected

| Choice | Rejected alternative | Why |
| ------ | -------------------- | --- |
| Seeded synthetic generator | Kaggle download | Not reproducible, can't control injected issues, GL wouldn't tie out |
| Medallion (4 layers) | One Big Table | No audit layer, couples ingestion+cleaning+modelling, untestable |
| `uv` | Poetry / pip | `uv` also manages the interpreter version and is far faster in CI |
| Portable SQL behind macros | BigQuery-native everywhere | Cheap Snowflake migration path; the brief asked for it |
| DuckDB as primary warehouse | — | Role is cloud-warehouse-centric; kept as a possible offline test target |
