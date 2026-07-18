# STTM-auto — SQLX ETL Generator & Execution Engine

Turn five structured documents — a source schema, a target schema, an STTM
(source-to-target mapping) workbook, a UDF reference, and a folder-hierarchy
spec — into a complete, runnable ETL pipeline for PostgreSQL, and take that
pipeline all the way to a validated load with one command per stage.

```
input/  (five documents you provide -- local only, see templates/sample-input/)
   │
   ▼
/generate   →  output/definitions/**, output/metadata/**, output/bootstrap/**
   │
   ▼
/review     →  static + live-schema checks, PASS / WARN / FAIL
   │
   ▼
/seed       →  reset source_db / intermediate_db / target_db (structure only, no data)
   │
   ▼
/execute    →  run bootstrap SQL, then the pipeline itself, against real PostgreSQL
   │
   ▼
/validate   →  schema + data + generation validation against the live databases
```

`/clean` resets the generated workspace (`output/`) at any point in that cycle.
`/start-sttm` is a read-only health check you can run at any point too — it
inspects where you actually are and tells you which command to run next.

## Why this exists

Reasoning about *what* a pipeline should do (parsing schemas, classifying
mappings, resolving lookups) is expensive and best done once. Rendering SQL
and running it against a database should be cheap, deterministic, and
repeatable. This project keeps those two concerns strictly separate:

- **`.claude/skills/sqlx-etl-generator/`** — the generator. Reasons about the
  five input documents exactly once per `/generate` run and produces a frozen,
  versioned intermediate representation (the *buildspec*) plus everything
  rendered from it. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design
  (ADR-001) and [`.claude/skills/sqlx-etl-generator/docs/README.md`](.claude/skills/sqlx-etl-generator/docs/README.md)
  for the practical guide.
- **`engine/`** — a standalone Python application, independent of any LLM, that
  executes what the generator produced: runs the generated SQLX against real
  PostgreSQL, prepares/tears down the databases involved, and validates the
  result. See [`engine/README.md`](engine/README.md).

Everything in between is deterministic and reproducible: identical input
documents always produce byte-identical generated output.

## The seven commands

| Command | What it does | Touches a database? |
|---|---|---|
| `/start-sttm` | Read-only health check: inspects input/output/database state and recommends the next command. Never generates, executes, or modifies anything. | No — read-only connectivity check only |
| `/clean` | Deletes `output/` (generated SQLX, metadata, bootstrap SQL). Never touches `input/`, source code, or tests. | No |
| `/seed` | Resets `source_db`, `intermediate_db`, `target_db` to fresh and empty. **Never inserts data.** | Yes — destructive (drops + recreates) |
| `/generate` | Regenerates `output/` from `input/`. Always a full replace, never a merge. | No |
| `/review` | Validates generated artifacts against rules the generator itself wrote, plus an optional live-schema cross-check. Never modifies anything. | Read-only (optional) |
| `/execute` | Runs `output/bootstrap/**` SQL, then the generated pipeline itself, against real PostgreSQL. | Yes |
| `/validate` | Final gate: schema, generation, and data checks against the live databases. Produces a PASS/WARN/FAIL report. | Read-only |

Defined in [`.claude/commands/`](.claude/commands/); each is a thin wrapper —
`/generate` and `/review` delegate to the skill's own plans, `/seed` and
`/execute` reuse `engine/dbadmin.py`, `/validate` reuses `engine/validate.py`,
`/start-sttm` reuses the skill's `check_input.py` plus the new
`engine/healthcheck.py`.

## Prerequisites

- Python 3.11+
- PostgreSQL (tested against 17), reachable with a superuser or equivalent role
- `pip install -r engine/requirements.txt` and
  `pip install -r .claude/skills/sqlx-etl-generator/scripts/requirements.txt`
- Connection details available either via a `postgres`-named entry in `.mcp.json`
  or the standard `PGHOST` / `PGPORT` / `PGUSER` / `PGPASSWORD` environment
  variables (see `engine/postgres.resolve_connection_config` — never hardcoded)

**Local-only config files you create yourself after cloning** — none of
these are tracked in Git (all gitignored), so a fresh clone has none of
them:

| File | Needed for | Notes |
|---|---|---|
| `.env` | Postgres credentials | `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`. Auto-loaded by every command that touches Postgres (`/seed`, `/execute`, `/validate`, `/start-sttm`) via `python-dotenv`. Simplest option — see `ONBOARDING.md` §2. |
| `.mcp.json` | Optional: Postgres via an MCP server instead of `.env` | Claude Code's MCP server config; a `postgres`-named entry here is preferred over `.env` if present. Not required if `.env` already has what you need. |
| `.env.mcp` (or similar) | Optional: your MCP client's own secrets | Only relevant if your MCP server needs a separate env file to launch — a convention of your MCP client, not this repository's own code. |

New to the repo? Start with [`ONBOARDING.md`](ONBOARDING.md) — it walks through
cloning, configuring PostgreSQL, and running the full cycle end to end. Or
just run `/start-sttm` — it looks at what's actually on disk and in
PostgreSQL and tells you what to do next.

## Repository layout

```
input/                          local working directory (gitignored except .gitkeep) --
                                 put your five documents here
templates/sample-input/         tracked, real worked sample of the five documents
output/                         generated by /generate (gitignored)
.claude/
  commands/                     the six slash commands
  skills/sqlx-etl-generator/    the generator itself (plans, specialists, templates, schemas)
engine/                         standalone execution engine (no LLM dependency)
  dbadmin.py                    database reset + bootstrap SQL orchestration
  validate.py                  live schema/data/generation validator
  executor.py, planner.py, ...  the pipeline runner
  tests/                        pytest suite (engine/README.md "Testing")
ARCHITECTURE.md                 ADR-001 — the full design rationale
```

## License

MIT — see [`LICENSE`](LICENSE). Copyright Prem Thiyagarajan and Kapil Thiyagarajan.
