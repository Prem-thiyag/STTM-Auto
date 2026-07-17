---
name: run-sqlx-etl-generator
description: Run, smoke-test, and verify the deterministic core of the sqlx-etl-generator skill (STTM workbook parsing, SQLX template rendering, JSON Schema validation, bootstrap generation) — without needing an LLM in the loop. Use when asked to run/test/verify sqlx-etl-generator, check its scripts still work, reproduce its worked example, or debug a rendering/parsing/validation failure in that skill.
---

# Running sqlx-etl-generator's deterministic core

`sqlx-etl-generator` (`../sqlx-etl-generator/`, i.e.
`.claude/skills/sqlx-etl-generator/` from the repo root) is a Claude Code Skill:
four LLM-driven plans (`Generate`, `Review`, `Execute`, `Clean`) plus a
deterministic Python core (`scripts/`) that those plans shell out to for
everything that doesn't require judgment — parsing the STTM Excel workbook,
rendering SQLX from a buildspec, validating JSON against schemas, and
generating the `bootstrap/` SQL tree. **This skill drives that deterministic
core directly**, the same way the `Generate`/`Review` plans do internally, so
you can verify it without spinning up a full agent session.

All paths below are relative to `.claude/skills/sqlx-etl-generator/` (the
target skill's root), not to this skill's own directory.

## Prerequisites

Verified this session with Python 3.13.1 (invoked via the `py` launcher on
Windows — plain `python`/`python3` on this machine resolve to the Microsoft
Store stub, not a real interpreter; use `py` here, or `python3`/`python` on a
normal Linux/Mac setup where those aren't aliased):

```
py -m pip install -r .claude/skills/sqlx-etl-generator/scripts/requirements.txt
```

Installs `openpyxl`, `jsonschema`, `jinja2` — the only three dependencies the
whole deterministic core needs.

## Run (agent path) — the driver

The driver is `.claude/skills/sqlx-etl-generator/scripts/smoke_test.py`. It
runs the entire deterministic pipeline against the worked example checked into
`docs/examples/` and proves three things that matter for this skill's
architecture (ADR-001): the STTM parser's header-contract enforcement actually
rejects malformed input, every metadata artifact this skill can produce
validates against its own schema, and — the important one —
**`render_sqlx.py` and `gen_bootstrap.py` reproduce the checked-in reference
output byte-for-byte**, which is the concrete test of "Generate is
deterministic for identical inputs," not just an assertion of it.

```
cd .claude/skills/sqlx-etl-generator
py scripts/smoke_test.py
```

Verified output (this session, exit code 0):

```
sqlx-etl-generator smoke test - skill root: C:\Prem-1\STTM-auto\.claude\skills\sqlx-etl-generator

== 1. scripts/parse_sttm.py against the real fixture workbook ==
[PASS] parse_sttm.py exits 0 on a valid workbook
[PASS] parsed exactly 7 mapping rows
[PASS] multi-column source parsed as a list

== 1b. parse_sttm.py rejects a workbook missing required headers ==
[PASS] exits 2 on missing required headers
[PASS] error names the header contract

== 1c. parse_sttm.py accepts a legitimate sourceless (GENERATED) row and flags duplicates ==
[PASS] exits 0 on a both-blank source row
[PASS] sourceless row parses with source_table/source_column both null
[PASS] sourceless row is not flagged duplicate
[PASS] unique target_column is not flagged duplicate
[PASS] both rows sharing (target_table, target_column) are flagged duplicate_mapping=true

== 1d. parse_sttm.py rejects a row with exactly one of Source Table/Source Column blank ==
[PASS] exits 3 on an inconsistent partial-source row
[PASS] error names the inconsistency

== 2. every checked-in reference artifact validates against its schema ==
[PASS] metadata\schema\source_schema.json valid
[PASS] metadata\schema\target_schema.json valid
[PASS] metadata\mapping\sttm.json valid
[PASS] metadata\dependency\dependency_graph.json valid
[PASS] metadata\execution\execution_plan.json valid
[PASS] metadata\execution\execution_log.json valid
[PASS] metadata\review\review_spec.json valid
[PASS] metadata\review\review_report.json valid
[PASS] metadata\cleanup\cleanup_manifest.json valid
[PASS] metadata\cleanup\cleanup_log.json valid
[PASS] metadata\manifest.json valid
[PASS] bootstrap\manifest.json valid
[PASS] both buildspecs valid

== 3. render_sqlx.py reproduces the checked-in definitions/ byte-for-byte ==
[PASS] render_sqlx.py exits 0
[PASS] re-rendered .sqlx files match docs/examples/generated-project/definitions/ exactly

== 4. gen_bootstrap.py reproduces the checked-in bootstrap/ (modulo timestamps) ==
[PASS] gen_bootstrap.py exits 0
[PASS] bootstrap/ matches reference exactly

== 5. render_sqlx.py renders a GENERATED (ROW_NUMBER) column correctly ==
[PASS] render_sqlx.py exits 0 for a GENERATED column
[PASS] GENERATED ROW_NUMBER column renders the expected qualified expression
[PASS] config block carries the version field

============================================================
ALL CHECKS PASSED
```

Run this after touching anything in `scripts/`, `templates/`, or `schemas/` —
it's the fastest way to know whether a template edit broke reproducibility.

## Direct invocation — each script standalone

Every command below was run individually while building and debugging this
skill; each is independently useful when you only want to exercise one stage.

**Parse an STTM workbook:**
```
py scripts/parse_sttm.py docs/examples/sttm_workbook.xlsx --output /tmp/sttm.raw.json
```

**Validate any metadata artifact against its schema:**
```
py scripts/validate_schema.py docs/examples/generated-project/metadata/build schemas/buildspec.schema.json --glob "*.buildspec.json"
```

**Render SQLX from buildspecs:**
```
py scripts/render_sqlx.py docs/examples/generated-project/metadata/build \
    --templates-dir templates/sqlx \
    --output-dir /tmp/definitions \
    --schema schemas/buildspec.schema.json \
    --intermediate-database intermediate_db
```
Prints a JSON array of `{path, hash}` for every file written.

**Generate the bootstrap/ tree from a schema IR:**
```
py scripts/gen_bootstrap.py \
    --source-schema docs/examples/generated-project/metadata/schema/source_schema.json \
    --target-schema docs/examples/generated-project/metadata/schema/target_schema.json \
    --udf-doc docs/examples/udf.md \
    --templates-dir templates/bootstrap \
    --output-dir /tmp/bootstrap \
    --intermediate-database intermediate_db \
    --project-name retail-analytics-etl
```

**Hash a set of input documents (what the Artifact Generator does for
`metadata/manifest.json`):**
```
py scripts/hash_files.py docs/examples/source_schema.md docs/examples/target_schema.md docs/examples/sttm_workbook.xlsx docs/examples/udf.md docs/examples/folder_hierarchy.md
```

## Run (human / agent-plan path)

The four actual plans (`Generate`, `Review`, `Execute`, `Clean`) are **not**
scriptable the way the deterministic core is — `Generate` and `Review` require
real LLM reasoning (parsing free-form markdown, classifying STTM
transformation notes, resolving mappings). To exercise them, load
`sqlx-etl-generator` in a Claude Code session and ask in plain language, e.g.
"generate a SQLX ETL project from the docs in
`.claude/skills/sqlx-etl-generator/docs/examples/`" — see
`.claude/skills/sqlx-etl-generator/SKILL.md` and `plans/generate.md`. This
driver's job is narrower and complementary: proving the deterministic 90% that
those plans depend on hasn't regressed, without spending a single token doing it.

## Gotchas

- **`python3` / `python` resolve to the Windows Store stub on this machine,
  not a real interpreter** — they print an install-from-Store nag and exit.
  Use `py` (the Python Launcher for Windows), which correctly resolved to the
  real Python 3.13.1 install. On Linux/Mac this whole issue doesn't exist;
  use `python3` there.
- **Two real bugs were caught by this driver while building the skill, not by
  code review:**
  1. Source-column references in rendered SQLX were two-part
     (`fdw_<table>.<column>`) instead of three-part
     (`fdw_<database>.<table>.<column>`) — `render_sqlx.py` was calling
     `fdw_alias()` on a table name instead of looking up that table's
     database first. Silent and easy to miss by inspection; caught instantly
     by the byte-for-byte reproducibility check once a real multi-source-table
     fixture existed.
  2. Jinja2's `trim_blocks=True` (set for otherwise-clean template output)
     strips the newline immediately after *any* block tag, including
     `{% endif %}` — so every comma-separated column list template
     (`{% for c in columns %}...{% if not loop.last %},{% endif %}\n{% endfor %}`)
     silently collapsed onto a single line. Fixed by pre-joining these lists in
     Python and having the template print the already-joined string, which
     sidesteps Jinja2 whitespace control entirely rather than fighting it with
     `{%- -%}` markers. If you add a new template with a comma-separated loop,
     follow the same pattern (see `scripts/render_sqlx.py`'s `staging_ddl` /
     `insert_column_list` / `select_expr_list` construction) instead of
     re-introducing an `{% if not loop.last %}` inside the loop body.
- **A third real bug, found by this same driver during a later repository
  refinement pass:** `parse_sttm.py`'s `main()` only ever returned exit code
  2 for any row- or header-level `ValueError`, despite the module docstring
  documenting exit code 3 for row-level validation failures specifically —
  the distinction was documented but never implemented. Fixed by splitting
  `ValueError` into two subclasses (`HeaderContractError`, `RowValidationError`)
  and catching the more specific one first in `main()`. Caught by `smoke_test.py`
  step 1d asserting the documented exit code, not by inspection.
- **`gen_bootstrap.py`'s `manifest.json` output includes a `generated_at`
  timestamp**, so a byte-for-byte diff against a reference will always differ
  there — `smoke_test.py` excludes that one field before comparing, nothing
  else.
- **Windows console + em dashes**: printing `—` (em dash) from a Python script
  can raise a `UnicodeEncodeError` or render as `�` depending on the active
  code page. `smoke_test.py` uses a plain hyphen in its own log output for
  this reason; templates that only ever get *written to a file* (never
  printed to a Windows console) can still use `—` safely, as several already
  do.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Python was not found; run without arguments to install from the Microsoft Store...` | `python`/`python3` aliased to the Store stub | Use `py` instead (Windows), confirmed working this session |
| `ModuleNotFoundError: No module named 'openpyxl'` (or `jsonschema`, `jinja2`) | Dependencies not installed | `py -m pip install -r scripts/requirements.txt` |
| `parse_sttm.py` exits 2 with "header contract violation" | The workbook's header row doesn't match `REQUIRED_HEADERS` in `scripts/parse_sttm.py` | Expected behavior, not a bug — see the printed list of missing columns and their accepted aliases |
| `render_sqlx.py` exits 4 citing a join referencing an unlisted table | A buildspec's `joins[].right_table` isn't in that buildspec's `source_tables` | Fix the buildspec (Mapping Resolver defect), not the renderer |
