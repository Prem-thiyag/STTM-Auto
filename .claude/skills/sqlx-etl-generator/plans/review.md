# Plan: Review

## Purpose

Validate a generated project against the rules `Generate` already wrote for it.
Review never invents a rule that isn't in `metadata/review/review_spec.json`, and
it never modifies `definitions/` or `metadata/` — it only ever writes
`metadata/review/review_report.json`.

## Preconditions

`metadata/review/review_spec.json` must exist (i.e. `Generate` has run at least
once for this project). If it doesn't, tell the user to run `Generate` first —
do not attempt to derive checks yourself.

## Process

1. Load `metadata/review/review_spec.json`.
2. Evaluate every check in order, each exactly as its `type` defines (see
   `specialists/artifact-generator.md` §2 for what each check type means — Review
   doesn't get to reinterpret a check type, only execute it):
   - `file_exists` — the `target` path exists.
   - `column_coverage` — every column in `expected_columns` appears in the
     corresponding `metadata/build/<TABLE>.buildspec.json`'s `columns[].target_column`.
   - `udf_reference_valid` — the named UDF appears in `bootstrap/db/03_intermediate/create_udfs.sql`
     (i.e. it was actually extracted from `udf.md` during Generate).
   - `dependency_order_respected` — `metadata/execution/execution_plan.json`'s step
     order matches `metadata/dependency/dependency_graph.json`'s `execution_order`.
   - `no_needs_review_mappings` — no `metadata/build/*.buildspec.json` contains a
     column with `transformation: "NEEDS_REVIEW"`. Any occurrence is `FAIL`, no
     exceptions — this is the backstop for every `NEEDS_REVIEW` the Mapping
     Resolver couldn't resolve.
   - `schema_cross_check` (only when `optional: true` is present, per ADR-001 §9)
     — **only run this if a read-only PostgreSQL MCP connection is available.**
     For each table referenced in `source_schema.json` (for `scope: source_db`) or
     `target_schema.json` (for `scope: target_db`), confirm the table and its
     columns actually exist in the live database. This is read-only: `SELECT`
     against `information_schema` or equivalent, nothing else — Review must never
     issue a write of any kind against any database, ever, under any check type.
     If the MCP connection isn't available or the database is unreachable, mark
     this check `WARN` with a detail explaining why — **never `FAIL`** for
     infrastructure Review doesn't control (ADR-001 §9 point 4).
3. **Drift check.** For every entry in `metadata/manifest.json`'s
   `generated_files`, hash the file on disk now and compare to the recorded hash.
   Any mismatch is a `drift[]` entry with `status: "MODIFIED_SINCE_GENERATE"`. This
   is informational, not a check failure by itself — a hand edit isn't necessarily
   wrong, but the user needs to know it happened before trusting `Execute`.
4. **Overall status.** `FAIL` if any non-optional check is `FAIL`. Otherwise `WARN`
   if any check (optional or not) is `WARN`, or if `drift` is non-empty. Otherwise
   `PASS`.
5. Write `metadata/review/review_report.json` (overwrite in full — this file
   reflects only the most recent Review run, it is not an append log).

## Constraints

- **Never modify a generated artifact**, under any circumstance, to make a check
  pass. If a check fails, the fix is a new `Generate` run (after fixing the
  underlying input document or specialist defect), not an edit to
  `definitions/` or `metadata/` from within Review.
- **Never write to any database.** The only database interaction Review ever
  performs is the read-only `schema_cross_check`.
- Report the `status` and every non-`PASS` check to the user in plain language —
  don't just say "see review_report.json."
