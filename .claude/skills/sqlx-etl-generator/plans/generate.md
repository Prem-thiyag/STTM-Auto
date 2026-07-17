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

Look in `input/` first. If it doesn't exist, or is missing one of the five
documents, **ask the user** for the missing path(s) rather than guessing a
substitute or silently falling back to some other location — do not search the
rest of the repository for a plausibly-named file. If the user gives explicit
paths (for either input or output), those override the defaults for that run;
this is a default, not a hardcoded location.

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
