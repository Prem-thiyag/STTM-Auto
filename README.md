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

Around that pipeline sits a second layer: turning a GitHub execution ticket
into a branch, running the cycle above, and raising a PR back with a durable
record of what happened. See [`WORKFLOW.md`](WORKFLOW.md) for the full
day-to-day practice, and [`CLAUDE.md`](CLAUDE.md) for the hard rules every
contributor's Claude Code session follows (most importantly: Claude never
runs a git/`gh` command that mutates state itself — it always prints the
command for you to run).

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

## The pipeline commands

| Command | What it does | Touches a database? |
|---|---|---|
| `/start-sttm` | Read-only health check: inspects input/output/database state and recommends the next command. Never generates, executes, or modifies anything. | No — read-only connectivity check only |
| `/clean` | Deletes `output/` (generated SQLX, metadata, bootstrap SQL). Never touches `input/`, source code, or tests. | No |
| `/seed` | Resets `source_db`, `intermediate_db`, `target_db` to fresh and empty. **Never inserts data.** | Yes — destructive (drops + recreates) |
| `/generate` | Regenerates `output/` from `input/`. Always a full replace, never a merge. | No |
| `/review` | Validates generated artifacts against rules the generator itself wrote, plus an optional live-schema cross-check. Never modifies anything. | Read-only (optional) |
| `/execute` | Runs `output/bootstrap/**` SQL, then the generated pipeline itself, against real PostgreSQL. | Yes |
| `/validate` | Final gate: schema, generation, and data checks against the live databases. Produces a PASS/WARN/FAIL report. | Read-only |

Every command above except `/clean` first runs a pre-flight check
(`tool/check_setup.py`) and stops with a plain pointer to `/setup` (and to
configuring `.env`) if dependencies or connection config aren't in place yet.

## The ticket & repo commands

| Command | What it does |
|---|---|
| `/setup` | One-time (or repeat-safe) local dev bootstrap: creates `./venv`, installs every Python dependency into it, installs `envmcp` if Node is available. |
| `/start-ticket <issue-number>` | Fetches a GitHub execution ticket's title/body/attachments, classifies attachments by content into `input/`'s five canonical filenames, prints (never runs) the branch-creation command. |
| `/finish-ticket <issue-number>` | Turns a ticket's real `/execute` + `/validate` telemetry into the committed `docs/event_log/**` record. |
| `/raise-pr <issue-number>` | Builds the PR title/body from the ticket's artifacts and asks whether to raise it via `gh` or the GitHub UI — never opens the PR itself. |
| `/review-digest` | Reasons across the latest `docs/collated/*.md` feedback digest and proposes what's actually worth fixing — triage, not auto-fix. |

Defined in [`.claude/commands/`](.claude/commands/); each is a thin wrapper —
`/generate` and `/review` delegate to the skill's own plans, `/seed` and
`/execute` reuse `engine/dbadmin.py`, `/validate` reuses `engine/validate.py`,
`/start-sttm` reuses the skill's `check_input.py` plus `engine/healthcheck.py`,
and the ticket/repo commands wrap the scripts in `tool/`. See
[`WORKFLOW.md`](WORKFLOW.md) for how they chain together end to end.

## Prerequisites

**Open this `STTM-Auto` folder itself as the VS Code workspace root — not a
parent folder.** Claude Code only discovers `.claude/commands/` relative to
the folder VS Code actually has open; if you open a parent directory (e.g.
`STTM-Auto`'s containing folder) with `STTM-Auto` as a subfolder, none of the
slash commands (`/start-sttm`, `/generate`, etc.) will show up, even though a
terminal `cd`'d into `STTM-Auto` looks correct.

- Python 3.11+
- PostgreSQL (tested against 17), reachable with a superuser or equivalent role
- Run `/setup` (or `python tool/setup_env.py`) — creates `./venv` and installs
  every Python dependency into it (`engine/requirements.txt` and
  `.claude/skills/sqlx-etl-generator/scripts/requirements.txt`), plus `envmcp`
  if Node is available. Every pipeline command checks for this itself and
  tells you to run it if it's missing, so you can also just start with
  `/start-sttm` and follow what it says.
- Connection details available either via a `postgres`-named entry in `.mcp.json`
  or the standard `PGHOST` / `PGPORT` / `PGUSER` / `PGPASSWORD` environment
  variables (see `engine/postgres.resolve_connection_config` — never hardcoded)
- **Node.js (with `npm`/`npx`)** — only needed if you're using the Postgres
  MCP server (`.mcp.json`), which loads its connection string via `envmcp`
  (`npm install -g envmcp`, one-time — see `ONBOARDING.md` §2). Not needed
  for the Python side (`/seed`, `/execute`, `/validate`, `/start-sttm`,
  `/generate`), which only ever uses `.env`.

**Local-only config files you create yourself after cloning** — gitignored,
so a fresh clone has none of them. Copy the tracked `.env.example` /
`.env.mcp.example` templates to get started:

| File | Needed for | Notes |
|---|---|---|
| `.env` | Postgres credentials for the Python side | Copy from `.env.example`. `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`. Auto-loaded by every Python command that touches Postgres (`/seed`, `/execute`, `/validate`, `/start-sttm`) via `python-dotenv`. This is what the engine actually reads — see `ONBOARDING.md` §2. |
| `.mcp.json` | Optional: Postgres via an MCP server instead of `.env` | Now tracked in git (no embedded credentials — just server launch config; the actual connection string lives in `.env.mcp`, still gitignored). A `postgres`-named entry here is preferred over `.env` if present. |
| `.env.mcp` | Required only if using the Postgres MCP server | Copy from `.env.mcp.example`. Holds the `DATABASE_URL` the MCP server connects with, loaded by `envmcp` (see the Node.js prerequisite above) — a separate credential path from `.env`, which the Python application never reads. |

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
  commands/                     the twelve slash commands (pipeline + ticket/repo)
  skills/sqlx-etl-generator/    the generator itself (plans, specialists, templates, schemas)
engine/                         standalone execution engine (no LLM dependency)
  dbadmin.py                    database reset + bootstrap SQL orchestration
  validate.py                  live schema/data/generation validator
  executor.py, planner.py, ...  the pipeline runner
  tests/                        pytest suite (engine/README.md "Testing")
tool/                           scripts behind the ticket/repo commands + local dev setup
  setup_env.py                  creates ./venv, installs everything into it (/setup)
  check_setup.py                stdlib-only pre-flight check every pipeline command runs first
  generate_event_log.py         turns real /execute + /validate telemetry into docs/event_log/**
  collate_feedback.py           twice-weekly digest of docs/session/** into docs/collated/**
  check_ticket_attachments.py   CI-side heuristic check behind .github/workflows/ticket-intake.yml
docs/
  session/, event_log/          per-ticket records, partitioned <year>/<quarter>/ -- see docs/README.md
  collated/                     periodic feedback digests (flat, dated)
.github/workflows/               collate-feedback.yml, ticket-intake.yml, tests.yml
ARCHITECTURE.md                 ADR-001 — the generator's design rationale
WORKFLOW.md                     day-to-day git/branching practice
CLAUDE.md                       hard rules every Claude Code session in this repo follows
```

## License

MIT — see [`LICENSE`](LICENSE). Copyright Prem Thiyagarajan and Kapil Thiyagarajan.
