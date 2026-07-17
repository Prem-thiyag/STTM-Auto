# Onboarding

A step-by-step walkthrough for getting this repository running from a fresh
clone, ending with a real, validated ETL run against PostgreSQL. If you just
want the concept overview, read [`README.md`](README.md) first; this document
is the practical "do this, then this."

## 1. Install prerequisites

- **Python 3.11+**
- **PostgreSQL** (developed and verified against 17). It needs to be reachable
  and you need a role with permission to create/drop databases (a superuser is
  simplest for local development).
- Python packages:
  ```
  pip install -r engine/requirements.txt
  pip install -r .claude/skills/sqlx-etl-generator/scripts/requirements.txt
  ```
  (`psycopg2-binary`, `jinja2`, `jsonschema`, `openpyxl`.)
- `psql` on your `PATH` — `/execute` and `/seed` shell out to it directly for
  bootstrap SQL and cross-database FDW setup.

## 2. Give PostgreSQL connection details

Nothing in this repository ever hardcodes a credential. Connection details are
resolved (`engine/postgres.py`'s `resolve_connection_config`), in order, from:

1. A `postgres`-named entry in `.mcp.json` at the repo root, or
2. The standard environment variables: `PGHOST`, `PGPORT` (default `5432`),
   `PGUSER`, `PGPASSWORD`.

For a local run, the simplest option is exporting the four environment
variables in whatever shell you invoke commands from:

```
export PGHOST=localhost PGPORT=5432 PGUSER=postgres PGPASSWORD=<your password>
```

## 3. Provide the five input documents

Everything the generator needs lives in `input/`:

| File | What it describes |
|---|---|
| `source_schema.md` | Tables/columns in the source database |
| `target_schema.md` | Tables/columns in the target database |
| `sttm.xlsx` | Source-to-target column mappings (the STTM workbook) |
| `user_defined_functions.md` | Any UDFs your mappings reference — **include the actual SQL body in a fenced ` ```sql ` block**, not just the signature. A UDF with no body compiles fine but fails the moment the pipeline actually calls it. |
| `folder_hierarchy.md` | Project name / expected output layout |

If you're adapting this repo to a new domain, replace these five files with
your own — nothing in `.claude/skills/sqlx-etl-generator/{specialists,templates,scripts}/`
names a business table, column, or domain term. See
`.claude/skills/sqlx-etl-generator/docs/README.md` for the full input format.

## 4. Run the cycle

```
/clean       # optional if output/ doesn't exist yet
/generate    # input/ -> output/definitions, output/metadata, output/bootstrap
/review      # validate what Generate produced; check the reported status
/seed        # reset source_db / intermediate_db / target_db (empty, no data)
```

At this point, **load your reference/test data into `source_db` yourself** —
this project deliberately never fabricates or auto-generates business data
(see `ARCHITECTURE.md` §5/§9). A plain `.sql` file with `INSERT` statements,
run with `psql -d source_db -f your_data.sql`, is the expected mechanism.
`test/data/` is a reasonable place to keep one.

```
/execute     # runs output/bootstrap/**, then the generated pipeline itself
/validate    # schema + data + generation checks against the live databases
```

Read `/execute`'s and `/validate`'s output carefully — both report exact
row counts and check-by-check status, not just a single pass/fail line.

## 5. Iterating

- Changed a source document? Re-run `/generate` — it always fully replaces
  `output/`, never merges with a prior run.
- Want a clean environment? `/clean` then `/seed` (note: `/seed` drops and
  recreates all three databases — anything loaded into `source_db` is lost).
- Something failed mid-`/execute`? The engine stops at the first failing step
  and rolls back that step's transaction — nothing partial is left committed
  for that stage. Fix the root cause (check
  `output/metadata/execution/engine_execution_log.json` for the exact error)
  and re-run `/execute`; bootstrap steps are idempotent (`CREATE ... IF NOT
  EXISTS`), so re-running is safe.

## 6. Things that bite people the first time

- **PostgreSQL folds unquoted identifiers to lowercase.** If you hand-edit a
  generated `.sql` file and add a quoted, mixed-case table name, cross-database
  FDW lookups (which compare a literal `table_name` option against the live
  catalog) will silently stop matching. Leave generated DDL unquoted, as
  produced.
- **Three separate databases, one PostgreSQL instance.** `source_db`,
  `intermediate_db` (staging), and `target_db` are expected to all exist on
  the same server — this isn't three different servers, just three
  databases the pipeline treats as logically separate.
- **`/seed` is destructive to `source_db`.** If you've manually loaded data,
  running `/seed` again wipes it. There's no confirmation prompt baked into
  the command itself by design (`/seed` is meant to be scriptable) — the
  slash command's own instructions ask for a sanity check first, but you are
  the actual safeguard.

## Where to go next

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the full design rationale (ADR-001)
- [`engine/README.md`](engine/README.md) — how the execution engine works
- [`.claude/skills/sqlx-etl-generator/docs/README.md`](.claude/skills/sqlx-etl-generator/docs/README.md) — the generator's own quickstart
- [`.claude/skills/sqlx-etl-generator/docs/ASSUMPTIONS.md`](.claude/skills/sqlx-etl-generator/docs/ASSUMPTIONS.md) — implementation decisions the ADR left open
