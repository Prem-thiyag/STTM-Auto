---
description: Regenerate the SQLX ETL project (definitions/, metadata/, bootstrap/) from input/ into output/.
---

Regenerate the ETL project from the five documents in `input/` (Source Schema,
Target Schema, the STTM workbook, User Defined Functions, Folder Hierarchy) into
`output/` — `definitions/` (per-table `read`/`process`/`write` SQLX), `metadata/`
(schema IR, mappings, dependency graph, buildspecs, execution plan, review spec,
cleanup manifest, project manifest), and `bootstrap/` (DDL, FDW bridges, UDFs, reset
scripts).

First, run `python tool/check_setup.py`. If it reports `[SETUP INCOMPLETE]`,
relay what it printed, tell the user to run `/setup` (and configure `.env`
from `.env.example` if that's what's flagged), and stop.

Otherwise, use the existing `sqlx-etl-generator` skill's Generate capability
(`.claude/skills/sqlx-etl-generator/plans/generate.md`) to do this — it already
implements the full pipeline; do not reimplement or bypass any part of it. `output/`
does not need to exist beforehand and is always fully replaced, never merged with a
prior run (this is Generate's own documented contract, not something this command
adds). When invoking the bootstrap-generation step, make sure `--buildspecs-dir
metadata/build` is passed so the cross-database FDW bridges render with real,
executable SQL rather than a placeholder.

On success, report: the target tables processed, where the five artifact
categories were written, and that `/review` should run next before `/execute` is
trusted. On failure (a dependency cycle, a schema-validation failure, a renderer
error), report the exact cause and stop — never write partial output.
