# Sample input

A real, worked set of the five documents `/generate` needs — Source Schema,
Target Schema, an STTM workbook, User Defined Functions, and a Folder
Hierarchy spec (a pharma-hospital domain, from this project's own first
non-fixture run — see `.claude/skills/sqlx-etl-generator/docs/ASSUMPTIONS.md`
"GENERATED columns are a first-class mapping type" for where it's referenced
elsewhere). Not synthetic filler — an actual example that has been run
through the full pipeline.

`input/` is local-only and gitignored (only `input/.gitkeep` is tracked), so
a fresh clone starts with nothing in it. To try the pipeline immediately:

```
cp templates/sample-input/* input/
/generate
```

To build your own project instead, replace these five files in `input/` with
your own — nothing in `.claude/skills/sqlx-etl-generator/{specialists,
templates,scripts}/` names a business table, column, or domain term, so any
domain works. Use these files as a format reference while you write yours;
`.claude/skills/sqlx-etl-generator/docs/README.md` documents the format each
one is expected to follow.
