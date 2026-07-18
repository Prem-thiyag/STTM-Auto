# Plan: Generate

## Purpose

Turn the five input documents into a complete SQLX ETL project: `definitions/`,
`metadata/`, and `bootstrap/`. This is the only plan that reasons about what the
pipeline should do — `Review`, `Execute`, and `Clean` only ever consume what this
plan writes.

## Preconditions

Default locations, relative to the repository root (not the skill directory):

- **Input**: `input/` — expected to contain the five source documents:
  1. Source Schema (markdown)
  2. Target Schema (markdown)
  3. STTM Workbook (`.xlsx`)
  4. User Defined Functions (markdown)
  5. Folder Hierarchy (markdown)
- **Output**: `output/` — where `definitions/`, `metadata/`, and `bootstrap/` are
  written.

Unless the user already gave explicit paths for all five documents, run
`python .claude/skills/sqlx-etl-generator/scripts/check_input.py [input_dir]`
first — it is the single source of truth for which five filenames are
required and whether each is present, non-empty, and (for the STTM workbook)
structurally parseable; nothing in this plan re-lists or re-checks them
independently. On a non-zero exit, relay its exact per-file messages (it
already points at `templates/sample-input/` for anything missing) and
**stop** — do not run any specialist, and do not guess a substitute or search
the rest of the repository for a plausibly-named file. `input/` is local-only
(gitignored except `.gitkeep`), so a fresh clone legitimately has nothing in
it until the user populates it. If the user gives explicit paths (for either
input or output) instead, those override the defaults for that run and skip
this check against `input/` — this is a default, not a hardcoded location.

## Rule: total regeneration, never merge

Every run of this plan **fully regenerates** `definitions/`, `metadata/`, and
`bootstrap/` from scratch. If the output directory already contains a prior
generation, this run replaces it entirely — do not read, merge with, or attempt to
preserve any part of a previous run's output (including hand edits — those will
already have been flagged as drift by a prior `Review` run; if the user wants to
keep a hand edit, that's a change to the *input documents* or the templates, not a
patch applied during Generate). This is what makes identical inputs always produce
identical output.

## Sequence

Run the six specialists **in this exact order** — each one's output is a
precondition for the next, and none of them may skip ahead and read a later
specialist's input:

| # | Specialist | Doc |
|---|---|---|
| 1 | Schema Parser (source) | `specialists/schema-parser.md` |
| 1 | Schema Parser (target) | `specialists/schema-parser.md` (same specialist, run again for the target doc) |
| 2 | STTM Parser | `specialists/sttm-parser.md` |
| 3 | Dependency Builder | `specialists/dependency-builder.md` |
| 4 | Mapping Resolver | `specialists/mapping-resolver.md` |
| 5 | SQLX Generator | `specialists/sqlx-generator.md` |
| 6 | Artifact Generator | `specialists/artifact-generator.md` |

Load each specialist's doc only when you're about to run that stage — this is
what keeps Generate's context usage proportional to the stage actually running,
not the whole pipeline's worth of instructions at once.

## Checkpoint: confirm unresolved database/schema names (after specialist 1, before specialist 2)

Schema Parser never guesses a database or schema name it can't trace to the
input documents (`specialists/schema-parser.md`) — a database name it couldn't
find falls back to the input filename stem (noted, not silent), and a schema/
namespace it couldn't find is left `null`. Immediately after both Schema
Parser runs (source and target) finish, and before STTM Parser runs, check
`metadata/schema/source_schema.json` and `metadata/schema/target_schema.json`
for anything left unresolved this way, and also decide the intermediate
database/schema this run will use (they aren't described by either document at
all — same reasoning as any other renderer parameter with a default, see
`references/naming-conventions.md`).

If every value is already explicit (both docs stated their schema, neither
database name fell back to a filename stem, and the user already told you what
intermediate database/schema to use for this run), skip this checkpoint
entirely and continue straight to specialist 2 — do not ask about something
already settled.

Otherwise, batch every unresolved item into **one** `AskUserQuestion` call
(one question per item, asked together, not one round-trip per item) before
running any further specialist. For each item, offer its
`references/naming-conventions.md` default as the option labeled
"(Recommended)" and "Provide my own" as the other option — never pick
silently, and never invent a default that isn't the documented one. Once
answered:

- Write the confirmed `schema` value back into `metadata/schema/source_schema.json`
  and/or `target_schema.json` (replacing `null`) — every specialist after this
  point must see only resolved, non-null values, per those files' own schema.
- Carry the confirmed intermediate database/schema forward as the
  `--intermediate-database` / `--intermediate-schema` arguments passed to
  `scripts/render_sqlx.py` (specialist 5) and `scripts/gen_bootstrap.py`
  (specialist 6) later in this same run.

This mirrors how this same plan already handles a missing input document path
(above, "Preconditions": ask, don't guess) and how the Mapping Resolver already
handles an ambiguous mapping (`NEEDS_REVIEW`, see `docs/ASSUMPTIONS.md`) — a
third, structurally identical instance of "stop and ask a human rather than
silently pick," not a new mechanism.

## Hard stops

Abort the run (produce no partial `definitions/`/`metadata/`/`bootstrap/` output)
and report the exact cause if:

- The Dependency Builder detects a cycle (`specialists/dependency-builder.md` §5).
- Any specialist's output fails validation against its schema in `schemas/`.
- The SQLX Generator (`scripts/render_sqlx.py`) exits non-zero for any buildspec.

A partial, half-consistent output is worse than no output — every downstream plan
assumes `metadata/manifest.json` existing means the generation it describes fully
succeeded.

## Postconditions

On success:
- `definitions/<TABLE>/{read,process,write}.sqlx` for every target table
- `metadata/**` fully populated except `metadata/review/review_report.json`,
  `metadata/execution/execution_log.json`, `metadata/cleanup/cleanup_log.json`
  (owned by `Review`, `Execute`, `Clean` respectively — Generate never writes
  them, and if they exist from a prior run in the same output directory, leave
  them alone; they describe history, not this run's structure)
- `bootstrap/**`

Tell the user Generate succeeded, list the target tables processed, and note that
`Review` should run next before anything in `Execute` is trusted.
