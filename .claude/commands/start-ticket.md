---
description: Fetch a GitHub execution ticket's title, body, and attachments; classify the attachments by content into input/'s five canonical filenames; print (never run) the branch-creation command.
---

Ticket number: `$ARGUMENTS`. If empty, ask which issue number before doing
anything else.

## 1. Fetch the ticket (read-only, run directly)

```
gh issue view $ARGUMENTS --json number,title,body
```

## 2. Find and download the attachments

GitHub renders drag-dropped, non-image files in the issue body as
`[filename](https://github.com/user-attachments/files/.../filename)` links
(images use `![...]()` with a UUID path instead — not expected for these
five documents, but handle it too if present). Extract every such URL from
the body text.

This repo is public, so a plain, unauthenticated fetch works:

```
curl -L -o .claude/tmp/ticket-$ARGUMENTS/<original-filename> <url>
```

(one call per attachment; create `.claude/tmp/ticket-$ARGUMENTS/` first if
needed — it's already gitignored, so this is a safe scratch location). If
fewer than 5 attachment-looking links are found, say exactly which of the
five documents seem to be missing and ask the user how to proceed rather
than guessing or continuing with partial input.

## 3. Classify each downloaded file — by content, never by filename

Ticket authors name their attachments however they like (`hierarchy.md`,
`healthcare_sttm.xlsx`, `udf_definitions.md` are real examples from this
repo) — never assume the name maps to its role, and never ask the user to
rename anything. Read each file yourself and decide:

- The one `.xlsx` file is always `sttm.xlsx`.
- Among the remaining documents: one describes folder/output layout or
  project naming (`folder_hierarchy.md`); one contains function
  signatures/SQL bodies for referenced transformations
  (`user_defined_functions.md`); two describe tables and columns
  (`source_schema.md` / `target_schema.md`) — disambiguate these two by
  cross-referencing which table names appear as mapping *sources* vs
  *targets* inside `sttm.xlsx`.
- If two files are genuinely ambiguous (could plausibly both be the same
  role), **stop and ask the user** — don't silently pick one. This mirrors
  how `NEEDS_REVIEW` works elsewhere in this repo (`ARCHITECTURE.md`'s
  Mapping Resolver): guessing wrong here is worse than asking.

## 4. Write canonical copies into `input/`

Plain filesystem writes (not a git action) — copy each classified file into
`input/source_schema.md`, `input/target_schema.md`, `input/sttm.xlsx`,
`input/user_defined_functions.md`, `input/folder_hierarchy.md`, overwriting
whatever's there now. Then delete the `.claude/tmp/ticket-$ARGUMENTS/`
scratch directory.

## 5. Confirm with the existing input checker

```
python .claude/skills/sqlx-etl-generator/scripts/check_input.py
```

Relay its output directly (it already prints one line per file plus the
workbook structural check) rather than re-describing it.

## 6. Print the branch-creation command — never run it

Per `CLAUDE.md`'s hard rule, this command never runs `git` itself. Compute a
branch name `execution/<issue-number>-<slug>` (slug: the issue title,
lowercased, non-alphanumeric runs collapsed to a single `-`, trimmed,
truncated to roughly 40 characters), then print exactly this block for the
user to copy and run themselves:

```
git checkout main
git fetch origin
git pull --ff-only origin main
git checkout -b execution/<issue-number>-<slug>
```

## Report

State: the issue title, the mapping from original attachment filename to
canonical role, `check_input.py`'s result, and the branch command block
above. If anything was ambiguous or missing, lead with that instead of the
branch command — an incomplete `input/` isn't ready for a branch yet.
