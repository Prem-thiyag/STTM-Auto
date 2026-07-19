---
ticket: 2
branch: execution/2-healthcare-etl
date: 2026-07-18
event_log: docs/event_log/2026/Q3/ISSUE-2_2026-07-18_healthcare-etl_log.json
---

# Session feedback: healthcare STTM ETL — generate → review → seed → execute → validate

**Scope:** First end-to-end run of the `sqlx-etl-generator` skill + `engine/` runtime against a real (synthetic) 6-table healthcare source → 5-table analytics target project. Full pipeline now runs clean (`/execute`: 15/15 steps; `/validate`: 222 PASS / 1 honest WARN / 0 FAIL).

This got there via three code fixes to the skill/engine itself (not just this project's generated output), one design call flagged and resolved with the user, and a couple of smaller frictions worth the repo owner's attention. Details below, most consequential first.

---

## Fixed this session (code changes, not project-specific)

### 1. `gen_bootstrap.py`: DDL creation order wasn't FK-topologically sorted

**File:** `.claude/skills/sqlx-etl-generator/scripts/gen_bootstrap.py`

`ddl_source_tables.sql` / `ddl_target_tables.sql` were rendered straight from `enrich_tables()`'s output, which preserves the schema IR's document order — i.e., whatever order tables happen to appear in `source_schema.md`/`target_schema.md`. Nothing reorders them by FK dependency before emitting `CREATE TABLE`.

Concretely: `doctors` was declared after `patients` but before `facilities` in this project's `source_schema.md`, and `doctors.facility_id` FKs to `facilities`. The generated DDL tried to `CREATE TABLE raw.doctors (... FOREIGN KEY (facility_id) REFERENCES raw.facilities ...)` before `raw.facilities` existed → hard failure on any real bootstrap run. Same latent bug exists for `ddl_target_tables.sql` (target hit it too: `dim_doctors` before `dim_facilities`).

**Fix:** added `topological_create_order()` (parent-first Kahn's algorithm over in-schema FK edges) and used it only for the two `ddl.sql.tmpl` render calls. Left `topological_reset_order()` (used by `reset.sql.tmpl`, which already uses `TRUNCATE ... CASCADE` so exact order isn't load-bearing there) untouched, to avoid any risk of changing `reset_source.sql`/`reset_target.sql`'s already-correct, already-tested output.

**Recommendation:** this will hit *any* project whose schema doc doesn't happen to declare tables in dependency order — which is a completely reasonable thing for a human-authored `source_schema.md` to do. Worth adding a regression fixture (two tables, child declared before parent) to `smoke_test.py`.

### 2. `engine/validate.py`: every live data query used unqualified table names

**File:** `engine/validate.py`, `validate_data()`

Every `SELECT`/`GROUP BY`/FK-orphan/UDF-cross-check query built its SQL from a bare table name (`stg_dim_doctors`, `dim_patients`, `patients`, etc.), relying on the connecting role's default `search_path`. This only works if a project happens to use PostgreSQL's default `public` schema for everything. Any project that (correctly, per `references/naming-conventions.md`) declares real schema names for source/intermediate/target — `raw`/`staging`/`analytics` here — hits `relation "..." does not exist` on the very first data check.

**Fix:** added an `--intermediate-schema` CLI parameter (default `"staging"`, mirroring `render_sqlx.py`/`gen_bootstrap.py`'s existing convention) and schema-qualified every live reference: staging table, target table, source base table, and FK-referenced target table.

**Recommendation:** `validate_generation()`/`validate_schema()` were unaffected because they query `information_schema` with an explicit `table_schema =` filter — the bug was isolated to `validate_data()`'s direct `SELECT ... FROM <table>` statements. Worth a smoke test that runs `/validate` against a project with non-`public` schemas (the checked-in reference fixture in `docs/examples/` uses `source`/`staging`/`warehouse` per its `source_schema.json` — worth double-checking whether the fixture's smoke test actually exercises `engine.validate`, since this bug shipped despite that fixture existing).

### 3. `engine/validate.py`: false-positive UDF correctness failures from a bad join-key heuristic

**File:** `engine/validate.py`, `validate_data()`

The UDF re-invocation cross-check needs to correlate a target row back to the exact source row it came from, to re-run the UDF against the *same* inputs. The old logic just grabbed "the first `DIRECT`-transformation column in the buildspec, whatever it is" as the join key — no uniqueness check at all.

For most tables in this project that happened to be a genuine natural key (`facility_id`, `insurance_id`, `appointment_id` all appear early and are unique) or, by luck, unique test data (`specialization` for `dim_doctors` — 8 doctors, 8 distinct specializations in this seed set, but would silently break the moment two doctors share a specialization). For `dim_patients`, there's no `DIRECT` passthrough of anything unique at all (`patient_bk` is itself UDF-derived) — the heuristic picked `gender` (2–3 distinct values), silently collapsed 12 patients into a couple of dict entries via key overwrite, and compared every patient's UDF output against essentially a random same-gender patient's source row. Result: **10/12 or 4/12 "mismatches" on every UDF column, with zero actual defects** — a validator bug producing false FAILs on correct data.

**Fix:** correlate via the source table's declared `primary_key` column instead — a genuine `DIRECT` passthrough of it preferred, a single-argument UDF applied to exactly that PK as fallback (computed via the same live UDF call, not assumed). When neither exists (`dim_doctors`: `doctor_bk` needs *two* source columns, `doctor_id` + `license_number`), the check now **WARNs honestly** ("no reliable join key found — skipping") instead of quietly reusing an unsound key and reporting a falsely-confident PASS or FAIL.

**Recommendation:** this is the highest-value fix of the three — a validator that can silently misreport both false-fail *and* false-pass depending on data shape undermines the entire point of `/validate`. Worth deciding, longer-term, whether the WARN-and-skip behavior is the right permanent answer, or whether it's worth teaching the join-key resolver to also try correlating via the domain/surrogate key (`_dk` columns) generated from a composite BK, which would cover `dim_doctors` too.

---

## Design gaps flagged, not code bugs — worth the repo owner's attention

### 4. No SCD2 / incremental template exists, despite the schema explicitly supporting it

`buildspec.schema.json` declares `load_strategy: scd2|incremental` as valid values, and `specialists/mapping-resolver.md` explicitly instructs setting them when a source doc says so ("do not helpfully downgrade it yourself") — but `render_sqlx.py`'s `SUPPORTED_LOAD_STRATEGIES = {"full_load"}` means it *will* fail loudly the moment that value is used. This project's `target_schema.md` genuinely declares two SCD2 dimensions and one incremental fact table (real, deliberate design, not a documentation slip) — meaning **this skill currently cannot generate a working pipeline for any project with an explicitly-SCD2 or explicitly-incremental target**, only `full_load` (truncate + reload) versions of them. This is documented as a known gap in `docs/EXTENSION_POINTS.md`, and the "ask the user, never silently downgrade" behavior worked exactly as designed — but it's worth flagging how *common* this will be in practice: SCD2 dimensions are a standard warehouse pattern, not an edge case.

### 5. Composed/nested UDF calls have no clean home in the buildspec schema

`buildspec.schema.json`'s `UDF` transformation type holds exactly one function name, and `render_sqlx.py` only renders it as a flat `udf_name(qualified_col1, qualified_col2, ...)`. But `udf.md`'s own documented usage examples for domain-key/hashdiff generation explicitly compose two UDFs: `udf_generate_dk(udf_calculate_patient_bk(patient_id), CURRENT_TIMESTAMP)`. This pattern is common enough that this one workbook uses it four times (both `_dk` and `_hashdiff` columns for two SCD2 dimensions). There's no way to express it via `transformation: "UDF"` today — I had to reclassify those four columns as `EXPRESSION` with a hand-written, fully-qualified raw SQL string instead, which works but loses the structural traceability (`udf` field, UDF-existence validation in Review's `C3` checks) that a `UDF`-typed column gets. Worth either documenting "compose via EXPRESSION, this is expected and fine" explicitly, or extending the schema to accept a call-chain.

### 6. `CURRENT_TIMESTAMP` passed into a UDF's `TIMESTAMP` parameter needs an explicit cast — undocumented gotcha

Same four columns above hit a second, more subtle issue: PostgreSQL's `CURRENT_TIMESTAMP` literal is typed `timestamptz`, but `udf_generate_dk`'s second parameter is declared plain `TIMESTAMP`. A column *assignment* (`SELECT CURRENT_TIMESTAMP AS _loaded_at`) tolerates the implicit cast; a *function argument* in overload resolution does not — `function udf_generate_dk(character varying, timestamp with time zone) does not exist`. Needed `CURRENT_TIMESTAMP::TIMESTAMP` in the `EXPRESSION` string. Not really an engine bug (correct SQL semantics), but worth a line in `references/naming-conventions.md` or `references/sqlx-syntax-guide.md` for anyone hand-writing an `EXPRESSION` that calls a UDF with a `TIMESTAMP` (not `TIMESTAMPTZ`) parameter.

### 7. `foreign_key` in the schema IR doesn't distinguish "DB-enforceable" from "informational lineage"

Both `dim_insurance.patient_bk` and `fct_appointments.patient_bk`/`doctor_bk` are documented in `target_schema.md` as FKs to another table's business-key column — but a business key on an SCD2 dimension isn't unique (multiple historical versions can share it), so PostgreSQL rejects a literal `FOREIGN KEY` constraint against it (`no unique constraint matching given keys`). `gen_bootstrap.py`'s `enrich_tables()` mechanically turns every non-null `foreign_key` into a physical DDL constraint with no check that the referenced column is actually unique. I resolved it by setting those three `foreign_key` fields to `null` (keeping the relationship in the column `description` instead) — schema-parser-faithful to what the document literally states, DDL-safe. This will recur for any SCD2-shaped target schema with fact tables joining on business keys (a standard Kimball pattern) — worth either a documented convention (schema IR only records DB-enforceable FKs; document business-key lineage in `description`) or a schema field like `foreign_key.enforced: bool`.

### 8. Manifest path convention (`generated_files[].path`) is ambiguous between repo-root-relative and `project_root`-relative

Not a code bug — `validate.py` and the reference fixture in `docs/examples/generated-project/metadata/manifest.json` both consistently use paths relative to `project_root` (no `output/` prefix, e.g. `"bootstrap/README.md"`). But `specialists/artifact-generator.md`'s instruction ("`generated_files` — the `{path, hash}` list `render_sqlx.py` printed") reads naturally as "relay exactly what the script printed" — and `render_sqlx.py`/`gen_bootstrap.py` print whatever path was passed to `--output-dir`, which is `output/definitions` etc. when invoked from the repo root (as documented everywhere, including this skill's own usage examples). Following the literal instruction produced a manifest with every path double-prefixed once `validate.py` joined it against `project_root="output"` — every file showed as "missing" in the drift check despite existing. Worth an explicit line in `artifact-generator.md`: paths must be relative to `--output-dir`'s own root, not to wherever the script happened to be invoked from.

---

## Smaller friction points

### 9. `check_input.py`'s required filenames are exact-match only

The five required filenames (`source_schema.md`, `target_schema.md`, `sttm.xlsx`, `user_defined_functions.md`, `folder_hierarchy.md`) must match exactly. My actual files were named `healthcare_sttm.xlsx`, `hierarchy.md`, `udf_definitions.md` — reasonable, self-descriptive alternates that just needed a plain filesystem rename. Minor, but worth a louder callout in `ONBOARDING.md`/`check_input.py`'s error message that names must match *exactly*, not just be recognizable.

> **Update (per `WORKFLOW.md` discussion):** going forward, ticket attachments are *not* renamed by the ticket author — `/start-ticket` classifies each attachment by content and writes canonical-named copies into `input/` itself. This friction point should not recur for tickets processed through that command.

### 10. STTM workbook header aliases didn't cover a natural real-world phrasing

`parse_sttm.py`'s `transformation_note` header aliases (`"transformation"`, `"transformation logic"`, etc.) didn't include `"transformation logic / udf call"` — a perfectly reasonable header the workbook author chose since the column carries both. Added it as a new alias (`scripts/parse_sttm.py` `REQUIRED_HEADERS`) rather than asking the user to rename their own spreadsheet column.

### 11. `doctor_bk VARCHAR(20)` vs. its own documented composite-key formula

Not a skill/engine bug — an inconsistency between two of *this project's* input documents. `target_schema.md` declared `doctor_bk VARCHAR(20)`, but `udf.md`'s own note for `udf_calculate_doctor_bk` documents the formula as `doctor_id + '|' + license_number` — which will exceed 20 characters for essentially any realistic license number (confirmed: all 8 in this test dataset did, 21–24 chars). Resolved by widening to `VARCHAR(50)` in both the input doc and generated schema, with the user's confirmation. Flagging only because **nothing in the pipeline catches this class of error before a live run** — Schema Parser and Mapping Resolver each look at their own document faithfully, but neither cross-checks a declared column width against what its own referenced UDF's documented formula could actually produce. Might be worth a `Review` check (`C7`?) that flags "this UDF-derived column's declared width looks implausibly narrow for its source columns' combined width," even as a `WARN`-only heuristic.

---

## Net result

Full pipeline runs clean end-to-end: `/generate` → `/review` (WARN, live-schema checks only) → `/seed` → `/execute` (15/15 steps, 46 rows total across 5 tables) → `/validate` (222 PASS / 1 honest WARN / 0 FAIL). All three code fixes are in `.claude/skills/sqlx-etl-generator/scripts/gen_bootstrap.py` and `engine/validate.py`, not project-specific output — they should hold for any future project using this skill.
