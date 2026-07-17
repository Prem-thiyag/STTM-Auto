# Naming Conventions

Normative rules every specialist must follow so that later, purely mechanical stages
(SQLX Generator, bootstrap generation) never have to guess or re-derive a name. These
conventions are infrastructure-level (databases, foreign schemas) or structural
(IDs, file paths) — none of them are domain business terms, so they apply unchanged
regardless of what source/target tables the user's documents describe.

## Foreign schema alias (cross-database reads via postgres_fdw)

Every cross-database read in generated SQLX goes through a `postgres_fdw` foreign
schema, never a hardcoded connection string. The alias for reading database `X` from
another database is always:

```
fdw_<X>
```

Example: reading `source_db` from `intermediate_db` uses the foreign schema
`fdw_source_db`. This is implemented by `fdw_alias()` in `scripts/render_sqlx.py`
and `scripts/gen_bootstrap.py` — both compute it the same way, so a buildspec never
needs to spell it out itself.

**The Mapping Resolver must use this convention directly** when writing any
`joins[].on` predicate or `columns[].expression` in a buildspec that references a
table outside the table currently being built (e.g. a `LOOKUP` expression reading an
already-loaded dimension table in `target_db` from a `process.sqlx` running against
`intermediate_db`). Example:

```json
"expression": "(SELECT dim.surrogate_key FROM fdw_target_db.dim_table dim WHERE dim.natural_key = stg_table.natural_key)"
```

The SQLX Generator never rewrites or qualifies table references inside `expression`
or `on` strings — they must already be fully resolved, fully qualified SQL when the
Mapping Resolver writes them into the buildspec.

## STTM mapping IDs

Assigned in workbook row order by the STTM Parser: `M001`, `M002`, ... zero-padded to
at least 3 digits, never reused, never renumbered on subsequent runs (a Generate run
always starts numbering from `M001` again since Generate fully regenerates every
artifact — stability across runs is not guaranteed or required).

## Execution / cleanup step IDs

`execution_plan.json` steps and `cleanup_manifest.json` entries are identified by
their position, not a semantic name — `step_id` is a plain incrementing string
(`"1"`, `"2"`, ...) assigned in `dependency_graph.execution_order`, um, order.

## LOOKUP helper columns

A `LOOKUP` column's staging row doesn't otherwise carry the natural-key value
needed to correlate against the looked-up table (the staging table is shaped
like the *target*, not the source). When a `LOOKUP` column's `source` is set,
`read.sqlx` lands that natural key under:

```
_lookup_<target_column>
```

**The Mapping Resolver must write `columns[].expression` for a `LOOKUP` column
to reference this helper column** (e.g.
`"(SELECT dc.customer_key FROM fdw_target_db.dim_customer dc WHERE dc.customer_key = stg_fact_order._lookup_customer_key)"`),
not the original source table — by the time `process.sqlx` runs, the helper
column is what's actually present on the staging row. See
`docs/examples/generated-project/definitions/FACT_ORDER/` for a worked example.

## `GENERATED` column generators

A `ROW_NUMBER`-type `generator.order_by` (see `schemas/buildspec.schema.json`
`$defs.generator` and `specialists/mapping-resolver.md`) is always a **bare
column name on the buildspec's first-listed `source_tables` entry** — never a
qualified reference, never a column on a different table. `scripts/render_sqlx.py`
qualifies it the same way it qualifies every other column reference; writing a
pre-qualified value here would be qualified twice.

## Staging table naming

The Mapping Resolver chooses `staging_table` per buildspec; the only hard rule is
that it must be unique across every target table in the same Generate run (the
Dependency Builder's cycle/uniqueness check will catch a collision). A recommended,
non-enforced convention is `stg_<target_table lowercased>`.

## File paths

- Generated SQLX: `definitions/<TARGET_TABLE>/{read,process,write}.sqlx` — table name
  used verbatim (as it appears in `target_schema.json`), not slugified, so it always
  matches the name a human sees in the schema document.
- Buildspecs: `metadata/build/<TARGET_TABLE>.buildspec.json`, same rule.
