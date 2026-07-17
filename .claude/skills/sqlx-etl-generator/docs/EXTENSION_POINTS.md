# Extension Points

This skill is deliberately not "finished" in the sense of never changing —
ADR-001 §11 names several directions it should grow in. This doc is the
practical guide for making those changes without quietly breaking the
architecture that makes the rest of it trustworthy.

## Hard boundaries — do not cross these, ever

- **Exactly four user-facing plans.** `Generate`, `Review`, `Execute`, `Clean`.
  A new capability is a new specialist inside `Generate`, a new check type in
  `review_spec.json`, or a new metadata artifact — never a fifth plan file
  under `plans/`.
- **`Execute` and `Clean` never run a command, infer an order, or regenerate
  anything.** If a change to either of them starts looking like "and then it
  decides X," that decision belongs in `Generate` or `Review`, not there.
- **`Review` never modifies a generated artifact.** If you're tempted to have
  Review "auto-fix" something it finds, that's `Generate`'s job on the next
  run, not Review's job on this one.
- **The SQLX Generator and Artifact Generator never read a source document.**
  If a new feature needs data that isn't in a buildspec (or another already-
  established artifact), the fix is adding a field to the *buildspec schema*
  (via the Mapping Resolver, the one place semantic judgment happens) — not
  giving a downstream specialist a new document to read.

## Adding a new `load_strategy` (e.g. incremental, scd2)

1. `schemas/buildspec.schema.json` already reserves the enum value — no schema
   change needed.
2. Add `templates/sqlx/write.<strategy>.sqlx.tmpl` (and `read`/`process`
   variants if the strategy needs different landing/processing logic, e.g.
   incremental needs a watermark filter in `read.sqlx`).
3. Add the strategy to `SUPPORTED_LOAD_STRATEGIES` in `scripts/render_sqlx.py`
   and branch to the new template(s) in `render_table()`.
4. Update `specialists/mapping-resolver.md` if the new strategy needs new
   buildspec fields (e.g. a watermark column) — add them as new, optional
   fields on `buildspec.schema.json`'s column or top-level shape, never by
   overloading an existing field's meaning.
5. Update `references/sqlx-syntax-guide.md`'s `load_strategy` section.

**Never** make an unrecognized `load_strategy` silently fall back to
`full_load` — `render_sqlx.py` intentionally exits non-zero for that. Adding
a strategy means adding real support for it, not widening what "full_load"
quietly means.

## Adding a new SQL dialect (BigQuery, Snowflake, ...)

The buildspec IR and every Layer 1 specialist (Schema Parser through Mapping
Resolver) are dialect-agnostic by construction — they never emit dialect-
specific syntax. Only two things are dialect-specific:

1. `templates/sqlx/*.tmpl` and `templates/bootstrap/*.tmpl` — the actual SQL
   text (e.g. `postgres_fdw` is Postgres-specific; BigQuery would use a
   different cross-project query mechanism).
2. Column type strings, if the target dialect doesn't share PostgreSQL's type
   names — handle this as a mapping table consulted at render time
   (`scripts/render_sqlx.py`), not by asking the Schema Parser to translate
   types when it first reads `source_schema.md`/`target_schema.md` (those
   files should keep recording the type exactly as the user wrote it).

A new dialect is a new `templates/<dialect>/` directory plus a `--dialect` flag
on `scripts/render_sqlx.py` and `scripts/gen_bootstrap.py` selecting which
template directory to load. Nothing upstream of rendering changes.

## Adding a new `generator.type` (for `GENERATED` columns)

`schemas/buildspec.schema.json`'s `$defs.generator` enumerates `ROW_NUMBER`,
`SEQUENCE`, `UUID`, `DEFAULT` today (`docs/ASSUMPTIONS.md` "GENERATED columns
are a first-class mapping type"). Adding a new kind (e.g. a hash-based key):

1. Add the value to `generator.properties.type.enum` in
   `schemas/buildspec.schema.json`, plus any new fields the kind needs and an
   `if`/`then` entry requiring them (following the existing `ROW_NUMBER` →
   `order_by` pattern).
2. Add a branch to `render_generator_expression()` in `scripts/render_sqlx.py`
   that turns the new `type` into concrete SQL — this is the only function
   that needs to change; `build_render_context()` calls it generically.
3. If the new kind should also be reachable from a workbook note (not just
   hand-authored buildspecs), add it to `schemas/sttm.schema.json`'s
   `transformation` enum and to the sourceless-kinds list in both its
   conditional validation and `specialists/sttm-parser.md`'s classification
   table.

**Never** add a table-, column-, or business-specific `generator.type` — a
generator kind must be meaningful for any target table, the same rule as
templates and specialists generally (see "What domain-agnostic requires,"
below).

## Adding a new specialist

Ask first: **is this new reasoning, or new rendering?**

- **New reasoning** (a new kind of judgment call about *what* to build) means
  extending the Mapping Resolver, or — only if the new reasoning is genuinely
  independent of everything the Mapping Resolver already does, and produces
  its own artifact other specialists can treat as a frozen contract — a new
  specialist inserted between the Dependency Builder and Mapping Resolver.
  Give it its own file under `specialists/`, its own schema under `schemas/`,
  and update `plans/generate.md`'s sequence table. It must not read anything
  the existing pipeline doesn't already make available to it, and its output
  must be a versioned JSON artifact other specialists can validate against,
  not a stream of prose.
- **New rendering** (a new deterministic output derived from existing
  artifacts) is a new script under `scripts/` plus a new template — extend
  the Artifact Generator's step list, don't add a specialist. Rendering never
  needs an LLM call at all; if what you're building needs one, it's reasoning,
  not rendering, and belongs in the previous bullet.

Whichever it is: **every specialist's output gets a JSON Schema in
`schemas/`.** A specialist that "just returns some JSON" without a schema is
not following this architecture — nothing downstream would have a contract to
validate against, which is exactly the invented-rules problem ADR-001 exists
to avoid.

## Adding a sixth input type (e.g. sample data)

See `docs/ASSUMPTIONS.md` "No sample data is ever fabricated" for why this
isn't supported today. If added: a new specialist (`Sample Data Parser`,
following the STTM Parser's deterministic-script-first pattern if the input
format is spreadsheet/CSV-shaped) producing a new schema-validated artifact
under `metadata/`, consumed only by the Artifact Generator's bootstrap-seed
step — `templates/bootstrap/seed_stub.sql.tmpl` gets a sibling template that
emits real `INSERT` statements once real data exists to put in them.

## What "domain-agnostic" requires of any change

Before merging any change to `specialists/`, `templates/`, or `scripts/`, grep
it for table names, column names, database names, or business terms. None of
those three directories should ever contain one — every such name must come
from a buildspec, a schema IR, or another artifact at render/reasoning time,
never from a literal in the skill's own code or prompts. `docs/examples/`
exists specifically to make violations of this easy to catch: it uses a
different domain than the one this skill was originally designed against, so
if a change only works for one domain's names, running the example will show it.
