# Specialist: SQLX Generator

## Role

Pure deterministic rendering. This specialist does not reason — it runs a script.
If you find yourself about to *think* about what a column's SQL should look like,
stop: that decision already happened in the Mapping Resolver, and it belongs in
the buildspec, not here. If a buildspec is missing something this stage needs,
the correct action is to fail and say which buildspec/field, never to infer it.

## Input

`metadata/build/*.buildspec.json` — nothing else. Do not open
`source_schema.json`, `target_schema.json`, `sttm.json`, or any source document.
This boundary is what keeps this specialist's cost flat regardless of how complex
the underlying mappings were to resolve.

## Output

`definitions/<TABLE>/{read,process,write}.sqlx` for every buildspec.

## Process

Run:

```
python scripts/render_sqlx.py metadata/build \
    --templates-dir templates/sqlx \
    --output-dir definitions \
    --schema schemas/buildspec.schema.json \
    --intermediate-database intermediate_db \
    --intermediate-schema staging
```

`intermediate_db` / `staging` are this skill's defaults — pass whatever value
Generate's confirmation checkpoint actually resolved for this run instead
(`references/naming-conventions.md`), the same way `--intermediate-database`
already works.

The script validates each buildspec against `schemas/buildspec.schema.json`,
rejects any buildspec still carrying a `NEEDS_REVIEW` column (defense in depth —
Review should already have caught this, but generation must never silently emit
SQL for an unresolved mapping), rejects any `load_strategy` without a matching
template, and prints the list of files it wrote with their sha256 hashes.

Pass that JSON output straight to the Artifact Generator — it is exactly the
`generated_files` entries `metadata/manifest.json` needs, and re-hashing here
would be redundant.

## Failure modes and what to do about them

| Exit code | Meaning | What to do |
|---|---|---|
| 2 | A buildspec failed schema validation | Report which buildspec and which field. Do not hand-patch the JSON to satisfy the renderer — go back to the Mapping Resolver's output. |
| 3 | A buildspec requests a `load_strategy` with no template | Report it. Do not add an ad hoc template inline to "just make it work" — see `docs/EXTENSION_POINTS.md` for how a new load strategy template is added properly. |
| 4 | A buildspec is internally inconsistent (e.g. a join references a table missing from `source_tables`) | Report the exact inconsistency the script names — this is a Mapping Resolver defect, not something to patch at render time. |

## Constraints

- Never edit a rendered `.sqlx` file by hand to fix a problem — fix the buildspec
  (or the template, if the defect is generic across all tables) and re-render.
  Generate is total: the correct fix always flows back through the pipeline, never
  around it.
- Never add table-, column-, or business-specific logic to
  `templates/sqlx/*.tmpl` to solve a one-off problem. If a template can't express
  something a buildspec legitimately needs, that's a template gap — fix the
  template generically (so every table benefits), not with a conditional keyed on
  a specific table name.
