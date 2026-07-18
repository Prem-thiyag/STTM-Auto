# Assumptions

ADR-001 fixes the architecture — four plans, six specialists, the ownership
model, the IR boundary. It does not fix every implementation detail; a few
things had to be decided while building this skill that the ADR left open.
Recorded here so they're traceable, not silently baked in.

## Generated `.sqlx` files carry a `config` block

Added when the standalone `engine/` runtime was introduced (see
`engine/README.md`): every `.sqlx` file now opens with a machine-readable
`config { "stage", "buildspec", "database", "version" }` block, documented in
`references/sqlx-syntax-guide.md`. This is a rendering-format change to
`templates/sqlx/*.tmpl` and `scripts/render_sqlx.py` only — no specialist
reasoning, plan behavior, or the buildspec IR itself changed. It exists purely
so `engine/parser.py` can determine what to run and against which database
without parsing SQL or re-deriving anything already decided upstream.
`version` (`"1.0"`, `scripts/render_sqlx.py`'s `SQLX_VERSION` constant) was
added during the repository refinement pass that also made
`execution_plan.json` declarative — it identifies the config block's own
format, is optional on parse (so older/hand-written files stay valid), and is
always emitted by the current generator.

**Why `database` stays in the config block even though `execution_plan.json`
also carries it now:** this was an explicit, considered choice, not an
oversight (see the next section) — a `.sqlx` file is meant to be
self-describing on its own, independent of whether an execution plan is even
present alongside it (e.g. a file opened directly, or copied elsewhere for
inspection). The engine cross-checks the two agree rather than trusting either
alone (`engine/README.md` "Declared vs. observed database";
`engine/executor.py`'s `_run_step`).

## Cross-database data movement uses `postgres_fdw`

All three databases (source, intermediate, target) are plain PostgreSQL. Rather
than invent an external "copy rows between databases" mechanism — which would
need its own orchestration/reasoning layer, exactly what `Execute` is designed
not to have — generated SQLX uses `postgres_fdw`: standard, built into
PostgreSQL, expressible as ordinary SQL a human can run with one `psql`/MCP
command. Bridge setup lives in `bootstrap/db/01_init/`. See
`references/naming-conventions.md` for the `fdw_<database>` alias convention
and `references/sqlx-syntax-guide.md` for how each of `read.sqlx` /
`process.sqlx` / `write.sqlx` uses it.

**Why not something else:** dblink is older and less capable than
`postgres_fdw`; an external copy step (e.g. a script invoked by `Execute`)
would violate "Execute never performs architectural reasoning" the moment it
had to decide *how* to move rows; a message queue or ETL-orchestrator
dependency would add infrastructure this skill has no business requiring.

## Read.sqlx creates the staging table, not process.sqlx

ADR-001 §5's bootstrap folder listing has a comment ("staging tables ... are
created at runtime by `process.sqlx`, not by bootstrap") that turns out to be
inconsistent with execution order: `read.sqlx` runs first and needs the table
to exist before it can `INSERT` into it. Treating that comment as prose
explaining *that bootstrap doesn't own it*, not a binding statement of *which
sqlx stage does*, `read.sqlx` issues `CREATE TABLE IF NOT EXISTS` before its
`INSERT`. This doesn't change anything ADR-001's ten numbered decisions
actually commit to.

## `LOOKUP` columns need a helper column in staging

Discovered while building the verification fixture (`docs/examples/`), not
anticipated at ADR time: a `LOOKUP` column's staging row doesn't otherwise
carry the natural-key value needed to correlate against the looked-up table,
because the staging table is shaped like the *target*, not the source.
`read.sqlx` lands that natural key under `_lookup_<target_column>` (see
`references/naming-conventions.md` "LOOKUP helper columns"); `write.sqlx`
never selects it, since it only reads the final `columns` list. This is an
additive convention on top of the existing `buildspec.schema.json` shape — it
did not require a schema change, only a documented naming rule.

## `intermediate_database` is a renderer parameter, not a buildspec field

`buildspec.schema.json` has `target_database` (per-table, since a project could
in principle have more than one target) but no `staging_database` — the
original business context fixed "one intermediate_db for the whole system,"
which is infrastructure configuration, not a per-table or business-domain
fact. `scripts/render_sqlx.py` and `scripts/gen_bootstrap.py` both take
`--intermediate-database` (default `intermediate_db`) rather than reading it
from any buildspec field.

## UDF deployment is a bootstrap concern

`udf.md` supplies UDF *implementations* (fenced ` ```sql ` `CREATE FUNCTION`
blocks), not just names. The Mapping Resolver needs to know a UDF's name and
signature to decide whether to reference it in a buildspec, but *deploying*
the function into `intermediate_db` is a structural, one-time, environment-setup
concern — like schema DDL — not something that needs to be re-decided every
Generate run. `gen_bootstrap.py` extracts every fenced SQL block from `udf.md`
verbatim into `bootstrap/db/03_intermediate/create_udfs.sql`. This is a copy,
never a re-implementation: the UDF author's own SQL is authoritative, and
nothing in this skill parses or rewrites a UDF body.

## No sample data is ever fabricated

None of the five declared inputs carries row-level sample data, yet bootstrap
is expected to support "sample loading scripts." Rather than have an LLM
invent plausible-looking rows — which would misrepresent synthetic content as
real example data, and is a bad habit worth not establishing even for a test
domain — `templates/bootstrap/seed_stub.sql.tmpl` emits column-name scaffolding
with explicit `-- TODO` markers and zero values. See
`docs/FUTURE_ENHANCEMENTS.md` for the natural fix (a declared sixth input
type) if this becomes a real requirement.

## `project_name` fallback

`folder_hierarchy.md` is expected to state a project name; if it genuinely
doesn't, the Artifact Generator falls back to a derived name and must say so
in its output — never invents one silently. See `specialists/artifact-generator.md` §4.

## `execution_plan.json` is declarative — no shell commands

Added during a repository refinement pass, replacing an earlier design where
each step carried a fully-resolved `command` string (e.g.
`psql -d intermediate_db -f definitions/DIM_PATIENT/read.sqlx`). That tied the
plan to one specific execution mechanism, which became a real problem once the
standalone `engine/` runtime existed alongside the human-facing `Execute`
plan: a stored shell command is useless to `engine/`, which executes a step's
SQL directly, and baking in a `psql`-shaped string presumed every environment
uses `psql` rather than an MCP tool or something else. `execution_plan.json`
now carries only `step_id`, `table`, `stage`, `database`, `file`, and
`depends_on` — enough for *either* consumer to do its job, favoring neither.

`Execute` (`plans/execute.md`) still shows the user something copy-pasteable:
it formats `psql -d <database> -f <file>` itself, from the step's own fields,
as a fixed display-time template — this is a formatting rule, not a value read
from metadata, and requires no judgment call (a user on a non-`psql`
environment translates the substitution themselves). `engine/` needs no
command string at all.

**Note on `ARCHITECTURE.md`:** ADR-001's own illustrative `execution_plan.json`
example (§5) still shows the earlier `command`-bearing shape — the ADR itself
was deliberately left unamended (its four plans, six specialists, and
ownership model are unchanged), consistent with every other post-ADR
implementation decision recorded in this file. This entry is the authoritative
record that the shape shown in that one example evolved; `schemas/execution_plan.schema.json`
is the current source of truth for the artifact's actual shape, the same
relationship every other assumption in this document has to the ADR.

## GENERATED columns are a first-class mapping type

Discovered as a real gap while building this skill's first non-fixture
project (`input/` — a pharma-hospital domain with `ROW_NUMBER`-style surrogate
keys): `schemas/sttm.schema.json` originally required every mapping row's
`source_table`/`source_column` to be populated, so `scripts/parse_sttm.py`
hard-failed on any STTM row describing a generated column with no source
(a surrogate key, a UUID). The buildspec schema had no representation for this
either — the only workaround was writing a raw `ROW_NUMBER() OVER (...)`
SQL string into an `EXPRESSION` column with `source: null`, which worked but
buried the column's actual meaning ("this is a generated surrogate key")
inside an opaque expression string, indistinguishable from any other
hand-written SQL.

Fixed by adding sourceless mapping kinds at both IR layers:

- `schemas/sttm.schema.json`'s `transformation` enum gained `GENERATED`,
  `DEFAULT`, `SEQUENCE`, `UUID` (alongside the pre-existing `EXPRESSION`,
  `CONSTANT`), each requiring `source_table`/`source_column` to be `null`
  (enforced by an `if`/`then` schema conditional, not just documentation).
  `scripts/parse_sttm.py` now passes a workbook row with **both** Source
  Table and Source Column blank through as a legitimate sourceless row
  (`source_table: null, source_column: null`) instead of failing — it only
  still fails when **exactly one** of the pair is blank, which is genuinely
  inconsistent, not a sourceless mapping. See `specialists/sttm-parser.md`
  for the full classification table.
- `schemas/buildspec.schema.json`'s `column_mapping` gained `transformation:
  "GENERATED"` and a `generator` field — a semantic object (`{"type":
  "ROW_NUMBER", "order_by": "patient_id"}`, or `SEQUENCE`/`UUID`/`DEFAULT`
  variants), not a raw expression string. `scripts/render_sqlx.py`'s
  `render_generator_expression()` is the one place that turns a `generator`
  into concrete SQL. See `specialists/mapping-resolver.md` for the resolution
  rules and `schemas/buildspec.schema.json` `$defs.generator` for the exact
  shape.

This is additive: every pre-existing transformation kind (`DIRECT`,
`EXPRESSION`, `UDF`, `CONSTANT`, `LOOKUP`, `NEEDS_REVIEW`) is unchanged, and a
buildspec that never uses `GENERATED` looks exactly as it did before. The
real project's two surrogate-key columns (`DIM_PATIENT.patient_key`,
`FACT_PATIENT_VISIT.visit_key`) were migrated from the `EXPRESSION`
workaround to `GENERATED` + `generator: {"type": "ROW_NUMBER", ...}` as part
of this fix, closing the gap `engine/README.md` had previously documented
under "Known gaps."

**`UUID`'s `gen_random_uuid()` assumes PostgreSQL 13+** (native since 13; earlier
versions need the `pgcrypto` extension instead). Not configurable today — if a
target environment is on an older PostgreSQL, that's a `templates/sqlx/*.tmpl`
/ `render_sqlx.py` change (a `--pg-version` style flag), not something this
skill currently handles.

## Database schema/namespace is a resolved field, confirmed via a Generate checkpoint, never guessed

Originally every generated database used the Postgres default schema (`public`)
unconditionally — `scripts/gen_bootstrap.py` hardcoded `CREATE SCHEMA IF NOT
EXISTS public;` for source, intermediate, and target alike, and no table
reference anywhere in generated SQL was schema-qualified. This was a real gap:
a project whose source/target documents describe tables living under real
namespaces (e.g. `source.patient_master`, `warehouse.dim_patient`) had no way
to express that, and a project that said nothing about schema silently landed
in `public` with no signal that a choice had even been made.

Fixed by adding a top-level, nullable `schema` field to
`source_schema.schema.json` / `target_schema.schema.json`, and a
`target_schema` field to `buildspec.schema.json` (copied from the resolved
target schema, mirroring how `target_database` already works). `schema-parser.md`
sets it from an explicit "Schema: X" line in the document if present, `null`
otherwise — it never guesses `public`, `source`, `warehouse`, or anything else,
consistent with this specialist's existing "never invent a name" rule for
`database`. A `null` value is a precondition failure for every specialist
after Schema Parser, resolved by a new step in `plans/generate.md` ("Checkpoint:
confirm unresolved database/schema names"): after both Schema Parser runs
complete, any unresolved database/schema value (including the intermediate
database/schema, which isn't described by either input document at all) is
batched into one `AskUserQuestion` call, offering `references/naming-conventions.md`'s
documented defaults (`source` / `staging` / `warehouse`) as the recommended
option — never applied silently. This is the same shape as two pre-existing
patterns in this skill (an unresolvable input path: "ask the user" per
`plans/generate.md`'s Preconditions; an unresolvable mapping: `NEEDS_REVIEW`
below) — not a new escape hatch, a third instance of one.

`scripts/gen_bootstrap.py` and `scripts/render_sqlx.py` both now require a
resolved (non-null) schema and fail loudly (exit 2 / a buildspec validation
error) if one reaches them unresolved — by design, these deterministic
scripts have no way to ask a human themselves; resolution must already be
done by the time they run. **One schema per database is a real, current
limitation**, not a display choice: the schema IR has no way to put two
tables from the same document under different namespaces. See
`references/naming-conventions.md` "Database schema / namespace defaults" for
the full default table and the FDW-alias interaction (the `fdw_<database>`
local alias names the remote *database*, unaffected by this change; only the
`CREATE FOREIGN TABLE ... OPTIONS (schema_name '...')` / `IMPORT FOREIGN
SCHEMA ...` statements inside `bootstrap/` needed the real remote schema
name).

## Duplicate mappings are flagged mechanically, resolved as `NEEDS_REVIEW`

`scripts/parse_sttm.py` computes, per row, whether its
`(target_table, target_column)` pair appears more than once in the workbook,
and sets `duplicate_mapping: true/false` accordingly — a purely mechanical
count, no interpretation. `specialists/sttm-parser.md` instructs the STTM
Parser's classification step to route every row in a flagged group to
`NEEDS_REVIEW`, never to pick a "winner" itself; `sttm-parser.md` already said
not to silently resolve a genuine workbook duplicate (a pre-existing rule),
this only makes the detection deterministic instead of relying on the LLM
step to notice on its own.

## UDF-missing-implementation is a loud warning, not a silent empty file

`udf.md` may declare UDF signatures only (no fenced ` ```sql ` bodies) — this
was always valid input (the Mapping Resolver only needs a name and signature
to reference a UDF in a buildspec), but until this refinement pass,
`scripts/gen_bootstrap.py` produced an empty
`bootstrap/db/03_intermediate/create_udfs.sql` with no signal beyond a
one-line comment that could be easy to miss. It now also prints a `WARNING:`
to stderr and writes a more explicit warning into the generated file's header
comment, naming exactly what will fail (any buildspec column with
`transformation: "UDF"`) and what fixes it (add real implementations to
`udf.md`, re-run `Generate`). The generator still never fabricates a UDF
body — this is strictly a visibility improvement, not a new capability.
The real project's `input/user_defined_functions.md` (signatures only, no
bodies) is exactly the case this warning was built for.

## `input/` is local-only; the repository's real project moved to `templates/sample-input/`

Originally `input/` was tracked in Git, holding this repository's own real
project (the pharma-hospital domain referenced throughout this document) —
which made the repository project-centric: cloning it handed you someone
else's input, not a blank slate matching `output/`'s already-local,
gitignored model.

Fixed by moving `input/`'s five files to a new tracked `templates/sample-input/`
(history preserved via `git mv`) and making `input/` itself gitignored
except a tracked `input/.gitkeep` placeholder — the same shape `output/`
already had (`.gitignore`'s commented-out `output/*` / `!output/.gitkeep`
pattern, now the real, active pattern for `input/`). Nothing about the
five-document contract changed; only where the *tracked example* of it
lives. Every reference elsewhere in this skill's docs to "the real project's
`input/...`" describes what was true when written and is left as historical
record, not updated to `templates/sample-input/...`.

Added one new deterministic script, `scripts/check_input.py`, as the single
place the five required filenames are declared — `plans/generate.md`'s
Preconditions and the repository's `/start-sttm` command both delegate to it
rather than each re-listing or re-checking the filenames themselves. It
checks presence/non-emptiness for all five and, for the STTM workbook only,
shells out to the already-existing `parse_sttm.py` (omitting `--output`) to
catch a structurally broken workbook before any specialist runs — it does
not attempt semantic validation of the four markdown documents' content,
since that's the Schema Parser / STTM Parser / Artifact Generator
specialists' job (an LLM step), consistent with this project's existing
"never fabricate, never guess" rule.

The repository's new `/start-sttm` health-check command (`engine/healthcheck.py`)
determines which databases a generated project actually uses by reading the
distinct `database` values off its own `execution_plan.json` (via
`engine.planner.ExecutionPlanner`, already validated) rather than assuming
any fixed set of names — consistent with "Database schema/namespace is a
resolved field... never guessed," above.
