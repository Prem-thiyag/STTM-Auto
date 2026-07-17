---
description: Final quality gate -- validate STTM/metadata/SQL against live source and target schema and data. Produces a PASS/FAIL report.
---

Run the project's live validator:

```
python -m engine.validate output
```

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
