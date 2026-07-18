# Specialist: Mapping Resolver

(Named `Mapping Resolver`, not `Definitions Generator`, specifically to avoid
colliding with the generated project's `definitions/` folder — see ADR-001 §9.)

## Role

**This is the only specialist in the entire skill that makes semantic judgment
calls.** Every specialist before it (Schema Parser, STTM Parser, Dependency
Builder) extracts and structures; every specialist after it (SQLX Generator,
Artifact Generator) only renders. If you are looking for "where does the actual
ETL logic get decided," it is here, nowhere else.

Its job: produce one buildspec per target table — the canonical Intermediate
Representation defined by `schemas/buildspec.schema.json` — containing everything
the SQLX Generator needs to render `read.sqlx` / `process.sqlx` / `write.sqlx`
*without ever looking at a source document again*.

## Input

- `metadata/schema/source_schema.json`
- `metadata/schema/target_schema.json`
- `metadata/mapping/sttm.json`
- `metadata/dependency/dependency_graph.json`
- `udf.md` (the raw input document — this is the one specialist besides Schema
  Parser and STTM Parser that is allowed to read a source document directly,
  because UDF signatures are exactly the ambiguity this specialist exists to
  resolve)

## Output

One file per target table: `metadata/build/<TABLE>.buildspec.json`, each
validating against `schemas/buildspec.schema.json`.

## Process, per target table

1. **`target_table`, `target_database`, `target_schema`, `grain`.** From
   `target_schema.json` (`target_schema` is that file's top-level `schema`
   field, already resolved to a non-null value by Generate's confirmation
   checkpoint before this specialist ever runs — see `plans/generate.md`).
   `grain` is a one-sentence statement of the row grain — state it plainly (e.g.
   "one row per <the table's apparent primary-key entity>"); this is carried into
   generated SQLX as a header comment for humans, not used by any logic.

2. **`load_strategy`.** Default `"full_load"` unless a source document explicitly
   states an incremental or SCD requirement for this table, in which case set the
   corresponding enum value from `schemas/buildspec.schema.json` — but know that
   **no template exists yet** for anything but `full_load` (`render_sqlx.py` will
   refuse to render and exit non-zero). If you set a non-`full_load` value, say so
   plainly in your output summary so the user isn't surprised when rendering
   fails; do not "helpfully" downgrade it to `full_load` yourself.

3. **`source_tables`.** Every distinct `(database, table)` pair referenced by this
   target table's mappings in `sttm.json`, plus every table referenced by any join
   you add in step 6. Every table a join or a `DIRECT`/`UDF`/`EXPRESSION` column
   touches must be listed here — `render_sqlx.py` validates this and fails loudly
   if a join references a table missing from this list.

4. **`staging_table`.** Choose a name unique across every buildspec in this
   Generate run (recommended: `stg_<target_table, lowercased>` — see
   `references/naming-conventions.md`).

5. **`columns`.** One entry per `sttm.json` mapping row targeting this table:
   - `target_column`, `type` — from `target_schema.json`.
   - `transformation` — carry forward from `sttm.json` *unless* you cannot
     actually produce a concrete SQL rendering for it, in which case downgrade it
     to `NEEDS_REVIEW` here even if the STTM Parser classified it otherwise. This
     specialist is the last line of defense before generation — a buildspec must
     never claim a transformation it can't back with real SQL.
   - `source` — `{table, column}` (column may be a list for multi-column
     transformations), or `null` for `CONSTANT` and `GENERATED`.
   - `expression` — required (non-null) for `EXPRESSION`, `CONSTANT`, and
     `LOOKUP`; must be **fully-formed, fully-qualified SQL** ready to be inserted
     verbatim by the SQLX Generator. For `LOOKUP` specifically, this means a
     correlated subquery or join-friendly expression referencing the looked-up
     table through its `fdw_<database>` alias (see
     `references/naming-conventions.md`) — the SQLX Generator will not qualify or
     rewrite this string for you. Also set `source` to the natural-key column the
     lookup correlates on (single column, not a list); the SQLX Generator lands it
     into staging as `_lookup_<target_column>` at read time, and your `expression`
     must reference that helper column (`<staging_table>._lookup_<target_column>`),
     not the original source table — see `references/naming-conventions.md`
     "LOOKUP helper columns" for the exact contract and a worked example.
   - `udf` — required (non-null) for `UDF`, and must match a function name that
     genuinely appears in `udf.md`. If `sttm.json` names a UDF that doesn't exist
     in `udf.md`, this is a `NEEDS_REVIEW`, not a guess.
   - `generator` — required (non-null) when `transformation` is `GENERATED`;
     `null` otherwise. This is where `sttm.json`'s sourceless kinds
     (`GENERATED`, `DEFAULT`, `SEQUENCE`, `UUID`) get resolved into something
     the SQLX Generator can render — a semantic object, never a raw SQL string
     (that's what distinguishes `GENERATED` from `EXPRESSION`):
     - `sttm.json` transformation `GENERATED` → buildspec `transformation:
       "GENERATED"`, `generator: {"type": "ROW_NUMBER", "order_by":
       "<column>"}` in the overwhelmingly common case (a row-number surrogate
       key) — `order_by` is a bare column name on this table's primary source
       table (`source_tables[0]`), typically its natural-key column. If the
       workbook's note describes something `ROW_NUMBER` can't express, that's
       `NEEDS_REVIEW`, not a forced fit.
     - `sttm.json` transformation `SEQUENCE` → buildspec `generator: {"type":
       "SEQUENCE", "sequence_name": "<name>"}`, using the sequence name the
       workbook note gave. The sequence itself must already exist in the target
       database — provisioning it is a bootstrap/DDL concern, not this
       specialist's.
     - `sttm.json` transformation `UUID` → buildspec `generator: {"type":
       "UUID"}`.
     - `sttm.json` transformation `DEFAULT` → buildspec `generator: {"type":
       "DEFAULT", "default_value": "<literal>"}` — the literal SQL default
       value, exactly as you'd write a `CONSTANT`'s `expression`.
     - `sttm.json` transformation `CONSTANT` stays buildspec `transformation:
       "CONSTANT"` with `expression` set as before — `CONSTANT` was already a
       first-class buildspec kind before `generator` existed and does not
       route through it.
     For every `GENERATED` column, `source` and `expression` are both `null` —
     `generator` is the only place its production rule lives. See
     `schemas/buildspec.schema.json` `$defs.generator` for the exact required
     fields per `type`, and `docs/ASSUMPTIONS.md` "GENERATED columns are a
     first-class mapping type" for why this replaced writing a raw
     `ROW_NUMBER() OVER (...)` string into `EXPRESSION`.
   - Any row still `NEEDS_REVIEW` here is written into the buildspec as such —
     do not drop it, do not silently resolve it. The Review plan's check `C5`
     exists specifically to catch this before it reaches generation.

6. **`joins`.** Only needed when a target table's columns pull from more than one
   source table. Each join needs `left_table`, `right_table`, `type`
   (`INNER`/`LEFT`/`RIGHT`/`FULL`), and `on` — a fully-resolved SQL predicate using
   bare table names (the SQLX Generator FDW-qualifies `right_table` itself using
   `source_tables` to know each table's database; write `on` accordingly, e.g.
   `"<left_table>.id = <right_table>.foreign_id"`).

7. **`filters`.** Fully-formed SQL boolean predicates, applied at read time.
   Leave empty (`[]`) unless a source document states a filtering rule (e.g. "only
   active records", "exclude soft-deleted rows").

8. **`mapping_refs`.** Every `sttm.json` mapping `id` this buildspec drew from, for
   audit traceability.

## Constraints

- **No re-reading `source_schema.json`'s types to "fix" a target type**, or
  vice versa — each schema IR is authoritative for its own side.
- **Never invent a UDF, a join, or a filter that no input document implies.** If a
  target column has no corresponding `sttm.json` mapping at all, that is a gap to
  surface to the user, not one to fill with a guessed `DIRECT` mapping to a
  same-named source column.
- Validate every buildspec you write:
  `python scripts/validate_schema.py metadata/build/ schemas/buildspec.schema.json --glob "*.buildspec.json"`
