# Specialist: Schema Parser

## Role

Convert `source_schema.md` and `target_schema.md` — free-form but structured markdown
— into the normalized Schema IR defined by `schemas/source_schema.schema.json` and
`schemas/target_schema.schema.json`. Runs twice per Generate: once for source, once
for target, using the same procedure.

## Input

- The markdown file (source or target — whichever this invocation is for)
- Nothing else. Do not read the STTM workbook, UDF doc, or folder hierarchy doc —
  they carry no schema information this specialist needs, and reading them would
  waste context for no benefit.

## Output

Write exactly one file:
- `metadata/schema/source_schema.json` (validates against `schemas/source_schema.schema.json`), or
- `metadata/schema/target_schema.json` (validates against `schemas/target_schema.schema.json`)

## Process

1. Read the markdown file. Identify the database name it declares (look for an
   explicit heading or statement like "Database: X"). Also look for an explicit
   schema/namespace declaration (e.g. "Schema: X") — this is a separate line
   from the database name; every table in the document is assumed to share this
   one schema. **Do not invent or default either value here.** If the database
   name is genuinely absent, set `database` to the input's filename stem and
   note the fallback in the table `description` field of the first table (the
   fallback is traceable, not guessed). If the schema is absent, set `schema`
   to `null` — never guess `"public"`, `"source"`, `"warehouse"`, or anything
   else. Resolving a `null` schema (and confirming a filename-stem-fallback
   database name) is the Generate plan's job, not this specialist's — it asks
   the user once, after both Schema Parser runs complete (see
   `plans/generate.md`'s confirmation checkpoint). This specialist's only job is
   to report faithfully what the document does and doesn't state.
2. For each table the document describes, extract:
   - `name` — exactly as written in the document (case and punctuation preserved).
   - `description` — a one-line summary if the document provides one; `null` if not.
   - Every column: `name`, `type` (verbatim as declared — do not normalize or
     translate to a different dialect's type names here; that happens at render
     time, if ever, not during parsing), `nullable` (boolean; if the document marks
     a column `NOT NULL` or "required", `nullable: false`, otherwise `true`),
     `primary_key` (boolean), `foreign_key` (`{table, column}` if the document
     states one, else `null`), `description`.
3. Validate the result against the corresponding schema
   (`scripts/validate_schema.py metadata/schema/<file>.json schemas/<file>.schema.json`)
   before considering this specialist done. A validation failure means the parse is
   wrong — fix the parse, don't hand-edit the JSON around the schema.

## Constraints

- **Every field must trace back to the document.** If a column's nullability,
  primary-key status, or type isn't stated or clearly implied, do not guess — flag
  it in that column's `description` (e.g. `"nullability not stated in source
  document; defaulted to nullable"`) rather than picking silently. This specialist
  does not have a `NEEDS_REVIEW` escape hatch the way the Mapping Resolver does
  (schema parsing is meant to be low-ambiguity); if you find yourself genuinely
  unable to parse a table, stop and surface that to the user rather than emitting
  a guessed structure.
- **No cross-referencing the other schema file.** The source parse and the target
  parse are independent; do not use the target schema to "fill in" something
  missing from the source schema or vice versa.
- **No business-domain assumptions.** Never assume a column exists, or has a
  particular type or constraint, because "that's how it usually is" in some
  domain. Only what the document says.
