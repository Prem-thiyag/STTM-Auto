---
description: Final quality gate -- validate STTM/metadata/SQL against live source and target schema and data. Produces a PASS/FAIL report.
---

First, run `python tool/check_setup.py`. If it reports `[SETUP INCOMPLETE]`,
relay what it printed, tell the user to run `/setup` (and configure `.env`
from `.env.example` if that's what's flagged), and stop.

Otherwise, run the project's live validator:

```
python -m engine.validate output --intermediate-schema staging
```

`staging` is the default — pass whatever schema this project's Generate run
actually used for the intermediate database (same value given to
`/generate`'s `--intermediate-schema`, per `references/naming-conventions.md`
in the sqlx-etl-generator skill) if it differs.

This checks, against the actual live databases and the actual generated artifacts
(never assumed, never re-derived from the original input documents):

- **Generation** — every expected artifact exists, buildspecs validate against
  `schemas/buildspec.schema.json`, `execution_plan.json`'s order matches the
  dependency graph, no `NEEDS_REVIEW` columns remain, and generated files haven't
  drifted from `metadata/manifest.json`'s recorded hashes.
- **Schema** — every table/column `metadata/schema/{source,target}_schema.json`
  declares actually exists, with a matching type, in the live `source_db`/`target_db`.
- **Data** — row counts (staging vs. target), primary-key uniqueness, declared
  `NOT NULL` columns actually have no NULLs, declared foreign keys resolve to a real
  row, and — for any `UDF`-transformed column — the target value is cross-checked by
  re-invoking the actual UDF (already loaded into `intermediate_db`) against the same
  source values, never by reimplementing its logic.

It writes `output/metadata/validate/validation_report.json` and prints every check
with its status. Report the overall `PASS`/`WARN`/`FAIL` and every non-`PASS` check
in plain language. If `/seed` skipped loading data (or none has been loaded into
`source_db` yet), row counts will legitimately be zero — report that plainly as a
data-coverage caveat, not as a passing data validation.
