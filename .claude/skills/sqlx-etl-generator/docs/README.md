# sqlx-etl-generator

Generates SQLX-based ETL projects (PostgreSQL, read/process/write per target
table) from five structured input documents. Implements `ARCHITECTURE.md`
(ADR-001) at the repo root this skill was authored against — read that first if
you want the design rationale; this doc is the practical "how do I use it."

## What it needs

1. **Source Schema** (markdown) — tables/columns in the source database(s)
2. **Target Schema** (markdown) — tables/columns in the target database
3. **STTM Workbook** (`.xlsx`) — source-to-target column mappings
4. **User Defined Functions** (markdown, with fenced ` ```sql ` `CREATE FUNCTION`
   blocks) — any UDFs the mappings reference
5. **Folder Hierarchy** (markdown) — project name and expected output layout

See `docs/examples/` for a complete, real, verified set of these five inputs
(retail domain — customers and orders, not the pharma-hospital domain used
during this skill's design, deliberately, to prove nothing domain-specific
leaked into the reusable logic) and `docs/examples/generated-project/` for
exactly what `Generate` produces from them, byte-for-byte, checked into the
skill as a reference.

## Quickstart

```
pip install -r .claude/skills/sqlx-etl-generator/scripts/requirements.txt
```

Then, working with an agent that has this skill loaded, say what you want in
plain language — "generate a SQLX ETL project from these five documents,"
"review the pipeline you just generated," "walk me through executing it,"
"clean up the pipeline's tables." Each maps to exactly one of the four plans
in `plans/`; see `SKILL.md` for the mapping.

## The four plans, one sentence each

- **Generate** (`plans/generate.md`) — the only plan that reasons. Runs six
  specialists in sequence, fully regenerates `definitions/` + `metadata/` +
  `bootstrap/` every time.
- **Review** (`plans/review.md`) — validates what Generate produced against
  rules Generate itself wrote (`metadata/review/review_spec.json`). Never
  modifies anything.
- **Execute** (`plans/execute.md`) — shows you one command at a time from
  `metadata/execution/execution_plan.json`. Never runs anything itself.
- **Clean** (`plans/clean.md`) — same as Execute, for
  `metadata/cleanup/cleanup_manifest.json`.

## Why it's structured this way

Two rules explain almost every design choice in this skill:

1. **Reasoning happens exactly once**, inside `Generate`'s specialists, and its
   output is a frozen JSON contract (the *buildspec* — see
   `schemas/buildspec.schema.json`) that every later stage treats as the only
   source of truth. The `SQLX Generator` that turns a buildspec into actual
   `.sqlx` files is pure Jinja2 templating (`scripts/render_sqlx.py`) — no LLM
   call, no re-reading the original documents. That's what keeps rendering
   cost flat as the number of target tables grows.
2. **Nothing touches a database except a human, on purpose.** `Execute` and
   `Clean` only ever print a command and wait. `Review`'s only database
   interaction is a strictly read-only, optional cross-check.

## Verified, not just written

Every script in `scripts/` and every template in `templates/` was actually run
against the fixture in `docs/examples/` while this skill was built — not just
written and assumed correct. That run caught and fixed two real bugs (a
qualification bug in how source columns were referenced, and a Jinja2
whitespace-control bug that was collapsing multi-line SQL onto one line) before
they shipped. See `.claude/skills/run-sqlx-etl-generator/SKILL.md` for the
exact commands, so you can re-run the same verification yourself.
