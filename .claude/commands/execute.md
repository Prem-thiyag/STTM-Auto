---
description: Execute the generated ETL end to end against real PostgreSQL -- bootstrap SQL, then the pipeline itself, in dependency order.
---

Run the generated pipeline for real, with no manual step-by-step confirmation
(this command is the automated counterpart to the skill's human-in-the-loop
`plans/execute.md` — see `engine/README.md` "Automating Execute" for why that's a
deliberate, anticipated extension, not a bypass of it).

Gate check first: read `output/metadata/review/review_report.json` if it exists.
- `status: "FAIL"` — tell the user why, and get explicit confirmation before
  proceeding.
- `status: "WARN"` — mention it once, then proceed.
- missing — tell the user Review has never run and confirm they want to proceed
  without it.

Then, stopping immediately and reporting the exact cause on any failure:

1. `python -m engine.dbadmin bootstrap` — runs every `output/bootstrap/**` SQL file
   against the right database, in dependency order (schemas, source/target DDL, both
   FDW bridges, staging namespace, UDFs). Skips `seed_source_data.sql` (never
   fabricated data, see `ARCHITECTURE.md` §5/§9) — any reference dataset must already
   be in `source_db` before this step.
2. `python -m engine output` — runs every `definitions/<TABLE>/{read,process,write}.sqlx`
   in `metadata/execution/execution_plan.json` order, one transaction per file,
   stopping on the first failure. Logs to `output/metadata/execution/engine_execution_log.json`.

Report: the execution order that ran, total duration, rows affected per step (from
the engine's own output), and a clear success/failure summary. If step 1 or 2 fails,
diagnose the root cause from the actual error before reporting anything as done —
never report success because the command was invoked.
