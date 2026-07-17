# Specialist: Artifact Generator

## Role

The last specialist to run in Generate. Produces every remaining metadata artifact
and the `bootstrap/` folder — all deterministic renderings from artifacts already
produced upstream. Runs last specifically so it can hash the final, actually-written
`.sqlx` files for `metadata/manifest.json`.

## Input

- `metadata/dependency/dependency_graph.json`
- `metadata/build/*.buildspec.json`
- `metadata/schema/source_schema.json`, `metadata/schema/target_schema.json`
- `udf.md`, `folder_hierarchy.md` (the raw input documents — read only for the
  narrow purposes below, never for semantic re-derivation)
- The `render_sqlx.py` output (list of `{path, hash}` for every generated `.sqlx`
  file) from the SQLX Generator step that just ran
- The five input documents' file paths, to hash for `manifest.json.inputs`

## Output

- `metadata/execution/execution_plan.json`
- `metadata/review/review_spec.json`
- `metadata/cleanup/cleanup_manifest.json`
- `metadata/manifest.json`
- `bootstrap/**` (via `scripts/gen_bootstrap.py`)

Every one of these validates against its schema in `schemas/`.

## Process

### 1. `execution_plan.json`

Walk `dependency_graph.json`'s `execution_order`. For each node (`<TABLE>.<stage>`),
emit a step: `step_id` (position, 1-based, as a string), `table`, `stage`, `database`
(`buildspec.target_database` for `write`, `intermediate_database` for
`read`/`process` — the same value the SQLX Generator already wrote into that
file's `config` block, see `references/sqlx-syntax-guide.md`), `file`
(`definitions/<TABLE>/<stage>.sqlx`), and `depends_on` (step_ids of nodes this one
has an edge from).

**Deliberately no `command` field.** `execution_plan.json` is consumed by two
different things — the `Execute` plan (a human-in-the-loop display) and the
standalone `engine/` runtime (an automated executor) — and a stored shell
command or MCP invocation string would tie the plan to one specific execution
mechanism, which is exactly the coupling `docs/ASSUMPTIONS.md` and
`engine/README.md` exist to avoid. `Execute` formats its own display command
deterministically from a step's own fields (see `plans/execute.md`); the engine
never needs a command string at all, since it executes the `.sqlx` file's SQL
directly. See `docs/ASSUMPTIONS.md` "`execution_plan.json` is declarative."

### 2. `review_spec.json`

Emit the fixed check set below — always these, in this shape, for every Generate
run (this is what makes Review's rules generated, not invented):

```json
{
  "checks": [
    { "id": "C1", "type": "file_exists", "target": "definitions/<TABLE>/<stage>.sqlx" },
    { "id": "C2", "type": "column_coverage", "target_table": "<TABLE>", "expected_columns": [ /* from buildspec.columns */ ] },
    { "id": "C3", "type": "udf_reference_valid", "udf": "<name>" },
    { "id": "C4", "type": "dependency_order_respected" },
    { "id": "C5", "type": "no_needs_review_mappings" },
    { "id": "C6", "type": "schema_cross_check", "scope": "source_db", "optional": true }
  ]
}
```

Emit one `C1` per generated file, one `C2` per target table, one `C3` per distinct
UDF referenced across all buildspecs, `C4` and `C5` once each, and one `C6` per
database Review could plausibly cross-check (source and target). Assign `id`s
sequentially (`C1`, `C2`, ... — not grouped by type).

### 3. `cleanup_manifest.json`

One object entry per staging table (`database: intermediate_db`, `type: table`,
`command: "DROP TABLE IF EXISTS <staging_table>;"`) and one per target table
touched this run (`database: <target_database>`, `type: table`,
`command: "TRUNCATE TABLE <target_table>;"`). This is the pipeline's own run
artifacts — not the bootstrap/demo environment, which gets its own separate
manifest (see step 5).

### 4. `manifest.json`

- `project_name` — from `folder_hierarchy.md` if it states one, else a reasonable
  derived name; note the fallback if used.
- `skill_version` — this skill's version (see `SKILL.md` frontmatter).
- `inputs` — hash each of the five source documents:
  `python scripts/hash_files.py <path1> <path2> ...`
- `tables` — every target table name.
- `generated_files` — the `{path, hash}` list `render_sqlx.py` printed, plus this
  same specialist's own outputs once written (hash `execution_plan.json`,
  `review_spec.json`, `cleanup_manifest.json`, and everything under `bootstrap/`
  too, so Review's drift check covers the whole generated tree, not just the SQLX).

### 5. `bootstrap/`

Run:

```
python scripts/gen_bootstrap.py \
    --source-schema metadata/schema/source_schema.json \
    --target-schema metadata/schema/target_schema.json \
    --udf-doc <path to udf.md> \
    --templates-dir templates/bootstrap \
    --output-dir bootstrap \
    --intermediate-database intermediate_db
```

This writes `bootstrap/**` including its own `manifest.json` — a **separate file**
from `metadata/cleanup/cleanup_manifest.json` (bootstrap objects are demo/test
environment scaffolding; cleanup objects are per-run pipeline artifacts — never
merge the two, or `Clean` could end up capable of tearing down the environment
instead of just the pipeline's output). Also write `bootstrap/README.md` from
`templates/bootstrap/README.md.tmpl` (project name, table list, and the `psql`
invocation pattern for supplying FDW connection variables).

## Constraints

- Everything here is templating and mechanical aggregation over already-produced
  artifacts. If producing one of these files seems to require a *new* judgment
  call about the data (not just reshaping what's already decided), that judgment
  belongs in the Mapping Resolver, not here — stop and route it back upstream
  instead of deciding it in this specialist.
- `bootstrap/db/02_source/seed_source_data.sql` must never contain fabricated
  row values — `templates/bootstrap/seed_stub.sql.tmpl` already enforces this by
  construction (column scaffolding only); don't hand-add sample rows here either.
