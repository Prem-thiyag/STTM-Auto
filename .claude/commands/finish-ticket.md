---
description: Turn a ticket's real /execute + /validate telemetry into the committed docs/event_log/<year>/<quarter>/ISSUE-<id>_<date>_<slug>_log.json record.
---

Ticket number: `$ARGUMENTS`. If empty, ask which issue number before doing
anything else.

This is a thin wrapper around `tool/generate_event_log.py` — a deterministic
script, no reasoning involved. Don't reimplement its logic here.

## 1. Gather the arguments the script needs (all read-only)

```
git branch --show-current
```

The current branch is expected to look like `execution/$ARGUMENTS-<slug>`
(from `/start-ticket`) — take the `<slug>` portion directly from it rather
than recomputing one from the issue title, so the event log filename always
matches the branch that produced it. If the current branch doesn't match
that shape, stop and ask rather than guessing a slug.

Then check whether a narrative doc already exists for this ticket:

```
ls docs/session/*/*/ISSUE-$ARGUMENTS_*_feedback.md 2>/dev/null
```

(pass whatever single match is found as `--narrative-doc`; if none exists
yet, omit the flag — the event log can be generated before the narrative
writeup, they're independent).

## 2. Run the generator

```
python tool/generate_event_log.py --ticket $ARGUMENTS --branch <branch> --slug <slug> [--narrative-doc <path>]
```

If it exits with an error (missing `engine_execution_log.json` or
`validation_report.json`), relay that message plainly — it means `/execute`
and/or `/validate` haven't been run yet on this branch. Don't fabricate a
placeholder event log to work around it.

## Report

State the written file's path, and the execution/validation status summary
the script printed (step counts, PASS/WARN/FAIL breakdown). Then remind the
user that the next step is raising the PR — per `CLAUDE.md`'s hard rule,
ask whether they want the `gh` command or the GitHub UI before proceeding,
don't assume either.
