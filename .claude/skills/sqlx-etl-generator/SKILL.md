---
name: sqlx-etl-generator
description: Generate, review, execute, and clean SQLX-based ETL projects (PostgreSQL, read/process/write per target table) from Source Schema, Target Schema, an STTM workbook, User Defined Functions, and a Folder Hierarchy document. Use when asked to generate an ETL pipeline, build a SQLX project, review generated SQLX/metadata, walk through executing a generated pipeline, or clean up a generated pipeline's database objects. Domain-agnostic — works for any set of source/target tables described in the input documents, not tied to any specific business domain.
version: 1.0.0
---

# SQLX ETL Generator

Implements ADR-001 (`ARCHITECTURE.md` at the repo root this skill was authored
against). If you haven't read that ADR, the one-paragraph version: reasoning
(figuring out *what* to build) and rendering (writing the actual SQL) are strictly
separate. Reasoning happens once, in `Generate`'s specialists, and produces a
frozen JSON contract — the **buildspec** — that every later stage treats as the
only source of truth. `Review`, `Execute`, and `Clean` never re-read the original
documents and never reason architecturally; they read metadata `Generate` already
wrote and either validate it or ask a human to act on it.

## The four plans — this skill exposes exactly these, nothing else

| Plan | Doc | One-line job |
|---|---|---|
| **Generate** | [`plans/generate.md`](plans/generate.md) | Run the 6 specialists, fully regenerate `definitions/` + `metadata/` + `bootstrap/`. |
| **Review** | [`plans/review.md`](plans/review.md) | Validate generated output against `metadata/review/review_spec.json`. Never modifies anything. |
| **Execute** | [`plans/execute.md`](plans/execute.md) | Print exactly one command from `metadata/execution/execution_plan.json`, wait for the human to run it. |
| **Clean** | [`plans/clean.md`](plans/clean.md) | Same as Execute, for `metadata/cleanup/cleanup_manifest.json`. |

Load the corresponding plan file when a user asks for one of these — don't load
all four at once, and don't load a plan's file before you know which plan the
user wants. If a request doesn't map cleanly to one of these four, it's out of
scope for this skill; do not invent a fifth plan (see `docs/ASSUMPTIONS.md`).

**Default paths:** `Generate` reads the five source documents from `input/`
and writes `definitions/` + `metadata/` + `bootstrap/` into `output/`, both
relative to the repository root — see `plans/generate.md` Preconditions.
These are defaults, not hardcoded paths; explicit paths from the user always
win. A separate, independently runnable `engine/` at the repository root
(outside this skill, not part of it — see `engine/README.md`) executes
whatever `Generate` writes to `output/`; this skill never executes SQL itself.

## Everything else in this directory is support for those four files

```
sqlx-etl-generator/
  plans/            the 4 user-facing plans (above)
  specialists/       Generate's 6 internal stages — loaded only from within generate.md
  scripts/            deterministic Python: STTM parsing, SQLX rendering, schema
                      validation, bootstrap generation, hashing (requirements.txt
                      here too — pip install -r scripts/requirements.txt once)
  templates/sqlx/     read/process/write.sqlx Jinja2 templates — generic, no
                      table/column/business names ever
  templates/bootstrap/ DDL / reset / seed-stub / FDW / README Jinja2 templates
  schemas/            JSON Schema for every metadata artifact — the contract
                      Review validates against and every specialist writes to
  references/         naming conventions + SQLX output shape, for humans and
                      for specialists that need the convention spelled out
  docs/               README, assumptions, extension points, future enhancements,
                      a worked fixture example (docs/examples/)
```

Specialists and templates are **domain-agnostic by construction**: nothing in
`specialists/`, `templates/`, or `scripts/` names a table, column, database, or
business term. Every such name flows in from the five input documents at Generate
time. `docs/examples/` contains one illustrative fixture set (used to build and
verify this skill) — it is example content only, never referenced by any
specialist, template, or script.

## Prerequisites

```
pip install -r .claude/skills/sqlx-etl-generator/scripts/requirements.txt
```

(`openpyxl`, `jsonschema`, `jinja2` — verified working with Python 3.11+ via the
`py` launcher on Windows or `python3` elsewhere.)

## Start here

- New to this skill? Read `docs/README.md` first, then `ARCHITECTURE.md` (the
  ADR) if you want the full rationale.
- Adding a new specialist, a new load strategy, or a new SQL dialect without
  breaking the architecture? Read `docs/EXTENSION_POINTS.md` — it exists
  specifically so that's a documented, safe operation.
- Want to see the whole pipeline run against fixture input? See
  `docs/examples/` and the verified walkthrough in
  `.claude/skills/run-sqlx-etl-generator/SKILL.md`.
