---
description: Validate the generated project against the rules Generate wrote for it (metadata/review/review_spec.json). Never modifies anything.
---

First, run `python tool/check_setup.py`. If it reports `[SETUP INCOMPLETE]`,
relay what it printed, tell the user to run `/setup` (and configure `.env`
from `.env.example` if that's what's flagged), and stop.

Otherwise, use the existing `sqlx-etl-generator` skill's Review capability
(`.claude/skills/sqlx-etl-generator/plans/review.md`) to validate what `/generate`
produced. `metadata/review/review_spec.json` must exist (i.e. `/generate` has run at
least once) — if it doesn't, say so and stop.

Evaluate every check in `review_spec.json` exactly as documented (file existence,
column coverage, UDF-reference validity, dependency-order match, the
`NEEDS_REVIEW`-column backstop, and the optional live-schema cross-check when a
Postgres connection is available — degrade that one check to `WARN`, never `FAIL`,
if the database isn't reachable), run the manifest drift check, roll up an overall
`PASS`/`WARN`/`FAIL` status, and write `metadata/review/review_report.json`
(overwrite in full).

Never modify `definitions/` or `metadata/` to make a check pass, and never write to
any database. Report the overall status and every non-`PASS` check in plain
language — don't just point at the JSON file.
