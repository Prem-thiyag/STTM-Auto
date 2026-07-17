# SQLX Output Syntax Guide

Describes the shape of every file under `definitions/<TABLE>/` that
`scripts/render_sqlx.py` produces from `templates/sqlx/*.sqlx.tmpl`. This is a
reference for humans reading generated output and for anyone extending the
templates — the SQLX Generator specialist itself only needs
`specialists/sqlx-generator.md` and the templates.

## The three-file, three-database split

Each target table gets exactly one folder under `definitions/` with three files,
executed in this order (see `metadata/execution/execution_plan.json`):

| File | Runs against | Job |
|---|---|---|
| `read.sqlx` | `intermediate_db` | Create the staging table if absent, then land every `DIRECT` / `EXPRESSION` / `UDF` / `CONSTANT` column by reading source tables through a `postgres_fdw` foreign schema (`fdw_<source_database>`). |
| `process.sqlx` | `intermediate_db` | Resolve every `LOOKUP` column — the only column kind allowed to depend on another table's output — by `UPDATE`ing the staging table in place. Always ends with a `SELECT count(*)` sanity check. |
| `write.sqlx` | target database | Truncate and reload the target table from the staging table, read through `fdw_<intermediate_database>`. |

`LOOKUP` columns are deliberately excluded from `read.sqlx`: a lookup by
definition reads something this table's `process` stage depends on per
`dependency_graph.json`, which may not exist yet at `read` time.

## Why cross-database SQL, not an external copy step

All three databases are plain PostgreSQL reached through the same Postgres MCP
connection surface. Rather than invent an external "copy rows between databases"
mechanism (which would need its own reasoning/orchestration layer — exactly what
`Execute` is designed not to have), generated SQLX uses `postgres_fdw`: standard,
built into PostgreSQL, and expressible as ordinary SQL that a human can run with a
single `psql`/MCP command. The FDW servers, user mappings, and foreign schemas are
set up once by `bootstrap/db/01_init/` — see `references/naming-conventions.md` for
the `fdw_<database>` alias convention and `docs/ASSUMPTIONS.md` for why this
mechanism was chosen over the alternatives.

## `config` block

Every generated `.sqlx` file opens with a machine-readable `config { ... }`
block — a JSON object (quoted keys, so it parses as plain JSON once the
`config` keyword and its wrapping braces are located) — before any SQL:

```
config {
    "stage": "read",
    "buildspec": "metadata/build/DIM_CUSTOMER.buildspec.json",
    "database": "intermediate_db",
    "version": "1.0"
}

<SQL>
```

This is the contract the standalone `engine/` runtime (`engine/README.md`, at
the repository root, outside this skill) reads to know which buildspec a file
belongs to, which stage it represents, and which database to run it against —
without parsing or interpreting any SQL.

- `stage` — one of `read`, `process`, `write`. **Required.**
- `buildspec` — the canonical project-relative path (`metadata/build/<TABLE>.buildspec.json`,
  per `references/naming-conventions.md`), always, regardless of what path
  `render_sqlx.py` was actually invoked with. **Required.**
- `database` — `intermediate_database` for `read`/`process`, `target_database`
  for `write`. Included here (not left for the engine to re-derive from the
  buildspec) because `intermediate_database` is a renderer parameter, not a
  buildspec field (see `docs/ASSUMPTIONS.md`), so nothing else in `metadata/`
  records it. **Required.** The same value also appears in this table's
  `execution_plan.json` step (`docs/ASSUMPTIONS.md` "execution_plan.json is
  declarative") — a deliberate, small duplication the engine cross-checks
  rather than trusting either copy alone (`engine/README.md` "Declared vs.
  observed database").
- `version` — the config block's own format version, currently always `"1.0"`
  (`scripts/render_sqlx.py`'s `SQLX_VERSION` constant). **Optional** — a
  `.sqlx` file without one still parses; this lets a hand-written or
  older-format file stay valid without a forced migration. Bump this only if
  the config block's own JSON shape changes in a way `engine/parser.py` needs
  to distinguish between versions.

Everything from the blank line after the closing `}` onward is SQL, verbatim —
the engine sends it to PostgreSQL unmodified. No specialist or script in this
skill parses a `config` block back out of a `.sqlx` file; that parsing only
happens on the execution side, in `engine/parser.py`.

## Header comment block

Every generated file starts with a comment block stating: that it's generated
(do-not-hand-edit, with a pointer to how drift gets detected), which stage it is,
which table it targets, which database to run it against, and which STTM mapping
IDs it traces back to. This is not decorative — it is what makes a generated file
self-explanatory to a human running `Execute` without needing to open `metadata/`.

## `load_strategy`

`buildspec.json`'s `load_strategy` field is `full_load`, `incremental`, or `scd2`
(see `schemas/buildspec.schema.json`). Only `full_load` has a template today —
`write.sqlx.tmpl` guards on it explicitly, and `render_sqlx.py` refuses to render
(exit code 3) a buildspec requesting a strategy with no template. Adding a new
strategy means adding a new `{% if load_strategy == '...' %}` branch (or a
dedicated template file) — never making an untemplated strategy silently fall back
to `full_load` behavior.

## `GENERATED` columns

A buildspec column with `transformation: "GENERATED"` carries a `generator`
object instead of a raw `expression` string (`schemas/buildspec.schema.json`
`$defs.generator`) — e.g. `{"type": "ROW_NUMBER", "order_by": "patient_id"}`
for a surrogate key. `scripts/render_sqlx.py`'s `render_generator_expression()`
is the one place that turns each `generator.type` into concrete SQL
(`ROW_NUMBER() OVER (ORDER BY ...)`, `nextval(...)`, `gen_random_uuid()`, or a
literal default) and lands it in `read.sqlx` exactly like any other non-`LOOKUP`
column. See `docs/ASSUMPTIONS.md` "GENERATED columns are a first-class mapping
type" for why this exists as a semantic object rather than a pre-written
expression string.

## What templates never contain

No table names, column names, database names, or transformation logic are baked
into `templates/sqlx/*.tmpl` — every one of those comes from the buildspec at
render time. A template change should only ever be about *how* SQL is laid out,
never *what* SQL a particular table needs.
