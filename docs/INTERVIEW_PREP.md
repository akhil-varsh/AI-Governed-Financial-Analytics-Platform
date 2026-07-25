# Interview prep — Northwind analytics platform

How to talk about this project, and a bank of likely questions with the follow-ups
they tend to escalate into. Answers are written to be *said*, not read — lead with
the short version, go deeper only when pushed.

Everything here is grounded in what's actually in the repo. If you don't remember a
number, say the shape of it ("ties out to about twelve cents on a hundred-seventy
million") rather than inventing precision.

---

## Part 1 — How to present it

### The one-liner
"It's two things that fit together: a finance data warehouse that turns three
messy CSV feeds into a tested star schema, and an MCP server on top of it that lets
a CFO ask that warehouse questions through Claude Desktop — read-only, governed, and
audited, so an LLM can't write a wrong number or touch anything it shouldn't."

### The 90-second version (the arc)
1. **The problem.** A PE sponsor owns a mid-market retailer. Between board meetings
   they want revenue and margin by region, channel, and product category. The data
   lives in disconnected exports — POS, the ERP general ledger, a customer/product
   master — that don't agree on keys, spelling, or currency.
2. **The pipeline.** Medallion architecture with dbt: contracts reject bad files at
   ingestion, Silver cleans and conforms (dedup, region spelling, FX to USD, null
   keys), Gold is a Kimball star with two SCD2 dimensions, and finance marts sit on
   top. 195 tests in three tiers. Dagster orchestrates it, GitHub Actions runs it on
   every push.
3. **The governance layer.** Then the part I care about: instead of handing an LLM a
   SQL connection, I built a semantic metric catalogue so it asks for *net revenue*
   rather than writing the formula, and five layers of guards for the raw-SQL escape
   hatch, plus a full audit trail. I wrote the attack tests first and watched them
   succeed before building the guards.
4. **What's real.** Data's synthetic but realistic; the reconciliation, the SCD2
   history, the guards, and the audit are real and tested. I verified the numbers by
   asking Claude Desktop live and checking every figure against the warehouse.

### Which half to lead with
- If the JD stresses **MCP / AI**: lead with the governance story, treat the
  warehouse as "the thing it governs."
- If it stresses **data engineering / dbt / modeling**: lead with the medallion +
  SCD2 + testing, treat the MCP server as the payoff that proves the model is clean
  and query-safe.
- Either way, the sentence that ties it together: *the governance is only possible
  because the warehouse underneath is modeled and tested well.*

---

## Part 2 — Question bank

### Warehouse & modeling

**Q: Walk me through the architecture.**
Medallion, strictly layered. Bronze is raw landed data plus ingestion metadata,
append-only, no transformation. Silver is cleaned, typed, deduplicated, conformed —
one row per business entity per grain. Gold is a dimensional star for consumption.
Marts are business-facing models on top of Gold. Each layer lives in its own schema.

- *Sub: Why medallion and not just load-and-transform in one step?* Separation of
  concerns and auditability. Bronze is immutable, so if a number looks wrong I can
  replay from it and answer "was it the source or my logic?" without re-pulling.
- *Sub: Why not One Big Table?* OBT is fast to demo but couples ingestion, cleaning,
  and modeling into one untestable step with no conformed dimensions. I still expose
  wide, analyst-friendly shapes — but in the marts layer, built on the star, not
  instead of it.
- *Sub: How do the layers physically separate?* A custom `generate_schema_name`
  macro suffixes the target dataset per layer (`_bronze`, `_silver`, …), so dev, CI,
  and any per-developer sandbox stay isolated in one project.

**Q: Tell me about the star schema and grain.**
Two facts: `fact_sales` at one row per order line, `fact_gl` at one row per GL
posting. Conformed dimensions: customer, product, date, region, channel. Grain is
the first thing I fix per model, because everything else — measures, joins,
dedup — depends on it.

- *Sub: What are the measures on fact_sales?* Quantity, gross revenue, discount,
  net revenue, COGS, gross profit — all in USD, the reporting currency.
- *Sub: Degenerate dimensions?* `order_id` and `order_line_id` live on the fact as
  degenerate dimensions; there's no order dimension because there are no order
  attributes worth conforming.

**Q: You did SCD2 two ways. Explain.**
Deliberately, so I can talk about the tradeoff. `dim_customer` is hand-written SCD2
with `valid_from`/`valid_to`/`is_current` derived from the master extract dates —
so the dates are *business-effective*. `dim_product` uses a dbt snapshot. The key
difference is dating: a snapshot's check strategy stamps validity at *capture time*
(when the snapshot ran), not the business date.

- *Sub: So why does that matter?* Because `fact_sales` joins `dim_customer`
  point-in-time — the segment the customer was in *on the order date*. That needs
  business-effective windows. I proved it: a customer's pre-change orders roll up to
  the old segment, later ones to the new. A snapshot's run-time dates can't do that
  from pre-existing historical extracts.
- *Sub: How do you prevent overlapping validity windows?* Half-open intervals
  `[valid_from, valid_to)` where each version's `valid_to` is the next version's
  start, and there's a singular test asserting no customer has two windows that
  overlap — plus one asserting exactly one `is_current` per customer.
- *Sub: Why generate a surrogate key instead of a sequence?* `generate_surrogate_key`
  on `(customer_id, valid_from)` is deterministic and reproducible — a rebuild
  produces the same keys, which a sequence wouldn't. The natural key repeats across
  versions; the surrogate is unique per version.
- *Sub: How did you build snapshot history from old extracts?* Ran the snapshot
  three times, each pointing at the state as of one extract date, so its check
  strategy accumulated the real category/price changes. In production it runs on a
  schedule and accumulates going forward — the replay is a one-time backfill.
- *Sub: dim_product is SCD1 and SCD2?* Yes — SCD2 on category and list_price (from
  the snapshot), SCD1 on description (I overlay the latest value in the model). A
  single snapshot strategy can't express a per-column mix, so I combine snapshot +
  overlay.

**Q: How do you handle idempotency?**
Two independent mechanisms. Ingestion: each file's `_batch_id` is a SHA-256 of its
bytes, and the loader skips a batch already present — so re-running can't
double-load. Facts: `fact_sales` is an incremental model with a merge on
`order_line_id`, so re-running upserts instead of duplicating. Verified: a rebuild
holds 200,000 rows / 200,000 unique.

- *Sub: Why merge over delete+insert?* `order_line_id` is a clean unique key, so
  merge is the correct upsert — no reliance on a partition predicate, and no gap
  between a separate delete and insert.
- *Sub: Why `order_line_id` as the unique key specifically?* It's the true grain
  key — one physical row per order line — so upserting on it is exactly the grain,
  which is what makes the rebuild deterministic.
- *Sub: What's the incremental predicate?* Only pull rows with a newer `_loaded_at`
  than the max already in the table, so steady-state runs are cheap; the merge on
  the key handles correctness.

**Q: Walk me through your data quality strategy.**
Three tiers. Source: dbt `source freshness` plus schema tests on the raw tables.
Model: generic tests — unique, not_null, relationships, accepted_values — on every
model, which gives referential integrity and zero orphan FKs. Business: seven
hand-written singular tests. 195 tests total.

- *Sub: What are the business tests?* The GL-to-sales tie-out within a tolerance,
  no overlapping SCD2 windows, exactly one current version per entity, net revenue
  never wrongly negative, margin in a sane band, fact row count within 10% of
  source, and a consolidated no-orphan-FK check.
- *Sub: The tie-out uses a tolerance — isn't exact-zero better?* No, and this is a
  good one. The GL was generated from the sales facts, so they should agree — and
  they do, to within twelve cents on a hundred-seventy-three million. The gap is a
  rounding-convention difference: NumPy rounds half-to-even, the warehouse rounds
  half-away. A test that fails on twelve cents is a test people learn to ignore; a
  materiality tolerance asserts the thing that matters — the books agree — while
  ignoring rounding noise. That's how real reconciliations work.
- *Sub: How would you make it exactly zero?* Round both sides with the same
  convention — regenerate the GL using the warehouse's rounding, or round once at
  the end instead of per line. I chose the tolerance because it's more honest about
  how independent systems reconcile.

**Q: The contracts — what do they actually check, and what did you learn?**
Each feed has a YAML schema (required columns, types, nullability, value ranges) and
a pydantic validator that rejects a bad file before Bronze. The subtlety is that the
contract must *allow* the messiness Silver is built to clean — dupes, dirty region
spellings, null customer IDs, returns, mixed currency — while catching genuine
corruption.

- *Sub: Give an example of that line being tricky.* My first contract required
  `discount_amount >= 0`. That's wrong — a return produces a negative discount. The
  fix was to loosen the contract, not the data. It's the clearest example of
  allow-legal / reject-corrupt.
- *Sub: Why pydantic and not Great Expectations?* Heavy for five feeds, and GE's
  expectations would need the same allow-the-dirt tuning anyway. A ~250-line
  validator shares the exact contract objects the loader types from, and it's easier
  to read and explain. I'd revisit at more feeds or team size.

**Q: Why BigQuery *and* DuckDB?**
BigQuery is the documented production warehouse, but the free sandbox blocks the DML
that dbt snapshots and incremental merge need. Rather than force a billing account
or put cloud credentials in CI, the same model SQL runs on DuckDB locally and in CI.
It's an addition, not a substitution — BigQuery stays the target.

- *Sub: How do you keep the SQL portable across two engines?* All model SQL is
  ANSI, and the handful of vendor-specific functions live behind one macros file —
  `try_cast`, `date_trunc_month`, month/day-name, a string cast. Models call the
  macro, never the vendor function. It's greppable: a `SAFE_CAST` in a model is a
  bug.
- *Sub: What actually differs between the engines in your code?* The cast functions,
  and the incremental strategy — merge on BigQuery, delete+insert on DuckDB, chosen
  by `target.type`. Both are idempotent on the same key.
- *Sub: What would break moving to Snowflake?* Mostly the same macros file plus the
  adapter/profile. QUALIFY would be available but I avoided it for ANSI portability;
  I'd revisit that. The point of the seam is that it's an auditable diff, not a
  rewrite.

**Q: Orchestration and CI?**
Dagster models the pipeline as assets: a Python ingestion asset *produces* the dbt
source assets, so dagster-dbt automatically makes every source-reading model depend
on it — one scheduled job, lineage-first. CI runs on DuckDB (no cloud secrets):
lint → build → all tests, failing on any test failure.

- *Sub: Why Dagster over Airflow?* Asset-centric — the things it schedules are the
  tables, so lineage and freshness are first-class and dbt models map one-to-one via
  dagster-dbt. Airflow is task-centric; you'd rebuild the lineage story yourself.
- *Sub: A real CI bug you hit?* Running the CI recipe locally before pushing, the
  first `dbt build` errored: a cross-layer singular test (fact rows vs source rows)
  references both a Bronze model and `fact_sales`, and dbt's default eager selection
  tried to run it before `fact_sales` existed. Fixed with
  `--indirect-selection cautious` on the intermediate build. It was invisible on
  paper and obvious on execution — which is why I run things.

### MCP server & governance

**Q: What is MCP, in your words?**
The Model Context Protocol — an open standard for giving an LLM tools and context
through a server it talks to over JSON-RPC. The server exposes *tools* (functions
the model can call), *resources* (documents it can read), and *prompts*. Claude
Desktop is the client; my server is what it connects to.

- *Sub: Tools vs resources?* Tools are actions the model invokes with arguments and
  gets a result — `query_metric`, `execute_sql`. Resources are addressable documents
  it reads for context — my data dictionary and metric catalogue as markdown.
- *Sub: What transport, and why does it matter?* stdio — the server reads/writes
  JSON-RPC on stdin/stdout. That's why my audit log goes to a file and *stderr*, not
  stdout: stdout is the protocol channel, and logging there would corrupt the stream
  and break the connection. Small thing, breaks everything if you miss it.
- *Sub: How does Claude Desktop know the tools exist?* It calls `tools/list` on
  connect; FastMCP builds each tool's JSON schema from the function signature and
  type hints, and attaches the annotations.

**Q: Why a semantic layer? This is the part you said you care about — sell it.**
Because if the LLM answers "what was net revenue?" by writing SQL, it can
confidently produce a *wrong* number — sum gross instead of net, double-count an
SCD2 customer, use the wrong fiscal calendar. A plausible wrong number is worse than
no answer for finance. So metrics are defined in YAML — the SQL expression, allowed
dimensions and filters, the fiscal grain, a plain-English definition, an owner — and
the model asks for a *metric* by name. It can slice it, but it can't rewrite the
formula.

- *Sub: How does query_metric build SQL safely?* The dimension and filter *keys* are
  validated against that metric's allowlist — an unknown key is denied, not ignored.
  The filter *values* are bound as parameters, never concatenated. And the formula
  comes only from the YAML. So the caller controls *which* metric and *how* it's
  sliced, never the SQL.
- *Sub: Prove the parameterization matters.* There's a test: a filter value of
  `West'; DROP TABLE ...` ends up only in the params list, never in the SQL text; it
  runs as a literal that matches no region and returns nothing. The table is
  untouched.
- *Sub: You said it also encodes correctness, not just safety?* Right. The
  `customer_segment` dimension joins the SCD2 customer on the fact's surrogate key,
  so it's point-in-time automatically. `customer_count` counts distinct natural key,
  not surrogate, so SCD2 versions aren't double-counted. The February fiscal year
  comes from `dim_date`. Three things an analyst writing raw SQL has to remember,
  encoded once.
- *Sub: What if a metric needs a join even with no dimensions?* `customer_count`'s
  expression references `dim_customer`, so the metric declares a `required_joins` —
  joins always added regardless of grouping. The compiler dedups joins so requesting
  two fiscal dimensions doesn't join `dim_date` twice.
- *Sub: Isn't this just dbt's semantic layer / Cube?* Same idea, and that's the
  production answer. Mine is a dependency-light version so the demo is
  self-contained. I'd name Cube/dbt-SL as where I'd take it.

**Q: You still expose raw SQL. Walk me through how you make that safe.**
Five layers, each covering another's gap. Engine: DuckDB read-only, so it can't
write. Syntactic guard: strip comments, one statement only, must start with
SELECT/WITH, a keyword blocklist, and wrap every query as
`SELECT * FROM (…) LIMIT 1000`. Identifier guard: parse to an AST with sqlglot and
refuse any table outside the gold/marts allowlist. Protocol: read-only annotations.
Audit: log every call with its decision.

- *Sub: Why sqlglot instead of more regex for the schema check?* "Which tables does
  this query touch" is a parsing question, not a pattern-matching one — a join to a
  hidden table, a subquery, a CTE alias shadowing a real name all defeat regex.
  Parsing to an AST and walking the table nodes is correct, and it structurally
  rejects non-SELECT statements. A parse failure is itself a denial.
- *Sub: What does read-only NOT stop, so why do you need the other layers?* A
  read-only connection still allows reading `information_schema` or an internal
  `meta` schema; `COPY … TO 'file'` writes to the OS filesystem, not the DB;
  `read_csv('/etc/passwd')` reads local files; and nothing caps rows or runtime.
  Layers 2 and 3 close those.
- *Sub: How do you stop `read_csv` / file access?* It's on the blocklist as a
  whole word, alongside `read_parquet`, `glob`, `COPY`, `ATTACH`, `INSTALL`, `LOAD`.
  Those touch the OS, and read-only doesn't guard the OS.
- *Sub: Comment-obfuscated DDL, like `DR/**/OP`?* Comments are stripped first, so
  `SELECT 1 /**/; DR/**/OP …` becomes two statements with `DROP` — caught by the
  single-statement check and the blocklist.
- *Sub: The timeout — how?* A watchdog thread calls DuckDB's `interrupt()` after the
  limit; a runaway recursive CTE gets cancelled and returns a timeout denial. Tested.
- *Sub: You built the guards test-first — describe that.* I wrote the adversarial
  suite first against a stub that did no guarding — 22 attacks "succeeded" (a
  `SELECT *` returned all 200k rows, out-of-schema reads returned data). Then I built
  the guards until all 25 flipped to a specific, logged denial. Each test asserts the
  *reason*, not just that it raised.

**Q: Why is the audit log its own layer if it prevents nothing?**
Because prevention and accountability are different jobs. Before a finance or
compliance team lets an LLM near the warehouse they'll ask: who asked what, what was
blocked and why, can we prove it. Every tool call — allowed or denied — is one
structured JSON line: tool, arguments, generated SQL, rows, latency, decision,
reason. There's a log-analysis script that summarizes allow/deny and top denial
reasons.

- *Sub: Why log arguments even on denial?* Forensics — the blocked query is the most
  interesting line in a security log. If I only logged allowed calls I'd throw away
  the evidence an incident review needs.
- *Sub: One gotcha you hit with logging?* My first version used
  `basicConfig(force=True)`, which hijacked the root logger and let the MCP SDK's own
  logs leak into the audit file as non-JSON. Fixed with a dedicated, non-propagating
  logger — and there's a test asserting the log stays pure JSON so it can't regress.

**Q: You demoed it live. Were the numbers right?**
Every figure was exact against the warehouse — regional totals, the year-by-year
breakdown, the $173M total, customer count of 15,001. And it passed the tests I care
about: it refused a leading "Southeast was strongest, right?" with the correct
ranking, and it did a GL reconciliation correctly — no revenue metric exists, so it
dropped to the guarded SQL tool, handled the negative-credit sign convention, and
landed the $0.12 tie-out.

- *Sub: So it's fully trustworthy?* The *numbers* are — the semantic layer and guards
  guarantee that. The *narrative* isn't. In one run it invented a "Q2 spike" that
  wasn't in the data. That's the honest boundary: governance guarantees the figures,
  not the model's prose about them. Knowing exactly where your controls stop is the
  point.
- *Sub: Why 15,001 customers, not 15,000?* There's a sentinel `UNKNOWN` member for
  the ~600 sales lines whose customer ID was missing — I resolve them to an explicit
  bucket instead of dropping the revenue, so it's 15,000 real customers plus one.

### Tradeoffs, limits, and production

**Q: What are the honest limitations?**
The data's synthetic. Day-to-day runs on DuckDB, not BigQuery. And the MCP server's
warehouse is a read-only snapshot with no row- or column-level security — anyone who
reaches it can read any governed table — no auth at the MCP layer, no multi-tenancy.
Those are real next steps, and they're written up in the threat model rather than
pretended away.

- *Sub: How would you add row-level security?* At the semantic layer and the guard:
  attach an identity to the session, and inject a mandatory predicate (e.g. deal team
  X sees only their portfolio company) into every compiled query and every raw query
  the identifier guard rewrites — plus per-user metric/table allowlists.
- *Sub: The blocklist is a denylist — isn't that fragile?* Yes, and I say so. A new
  dangerous DuckDB function wouldn't be covered until added. That's why read-only
  (Layer 1) and the schema allowlist (Layer 3) are the allowlist-style backstops that
  don't depend on enumerating every bad verb. Defense in depth is exactly so no
  single denylist has to be complete.
- *Sub: What would you harden first for production?* Identity + row-level security on
  the MCP side; on the warehouse side, move execution to real BigQuery/Snowflake with
  a SELECT-only role (the Layer-1 equivalent), and swap the metric layer for Cube or
  dbt's semantic layer so definitions are shared with the BI tool.

**Q: Where did AI help and where didn't it?**
I used AI to move fast on scaffolding, boilerplate, and first drafts, in explicit
phases with a review after each. What stayed mine: the architecture, the security
model, and the verification — deciding *what* to prove and actually proving it. Every
claim in the repo is backed by a command I ran, not asserted, and the bugs I found
(the discount contract, the stdout-vs-stderr, the CI selection issue) came from
running things, not from the model.

- *Sub: How do you know the AI didn't hallucinate a wrong number into the docs?* I
  cross-checked. The docs' "0 blank descriptions" claim is verified by a script that
  diffs the catalog against the manifest; the tie-out was run in pandas and in the
  warehouse; the guards have 62 tests. I treat generated output as a draft to verify,
  the same as a junior's PR.

---

## Part 3 — Questions to ask them
- How does the team think about governing LLM access to sensitive financial data
  today — is it prompt-level, or is there a real control plane?
- Where does the semantic layer live for you — dbt, Cube, LookML, or in application
  code — and who owns metric definitions?
- Snowflake or BigQuery, and how do you handle SCD / historical correctness in
  reporting?

## Part 4 — If you don't know something
Say so, then reason. "I haven't implemented X, but the way I'd approach it is…"
lands far better than a confident wrong answer — which, fittingly, is the exact
thing this whole project is built to prevent an LLM from doing.
