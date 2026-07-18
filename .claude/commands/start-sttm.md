---
description: Read-only project health check -- inspects input/output/database state and recommends the next command. Never generates, executes, or modifies anything.
---

Run exactly two commands, nothing else:

```
python .claude/skills/sqlx-etl-generator/scripts/check_input.py
python -m engine.healthcheck
```

Both already print one compact line per check — relay their output directly
rather than re-deriving or re-describing each line; don't paste raw JSON from
any metadata file, these two commands already did the reading. Its only
database interaction is a read-only connectivity probe plus listing
`pg_database` — same read-only guarantee `/review`'s optional live-schema
check already has; never a write.

Then apply this precedence — evaluate top to bottom, stop at the first gate
that isn't met, and state **exactly one** recommended next command:

1. `check_input.py` exited non-zero → name the exact file(s) it flagged,
   point at `templates/sample-input/` (copy from there to get started, or
   use it as a format reference), stop here — nothing below is meaningful
   until input is fixed.
2. `healthcheck.py`'s `generation` check is not PASS → recommend `/generate`.
3. `review` is not PASS (missing, WARN, or FAIL) → recommend `/review`. If
   it's FAIL specifically, mention that a `FAIL` from `/review` usually
   means re-running `/generate` after fixing the underlying input, not just
   re-running `/review`.
4. `connectivity` is FAIL → explain Postgres isn't reachable (point at
   `.mcp.json` or `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`, per
   `ONBOARDING.md` §2) and stop — nothing past this point can be checked or
   run without a live connection.
5. Any `database-*` check is WARN ("not yet created") → recommend `/seed`.
6. `execution` is not PASS (missing or WARN) → recommend `/execute`. If it's
   FAIL, quote the exact failing table/stage/error `healthcheck.py` reported
   and say the root cause needs fixing before re-running `/execute`.
7. `validation` is not PASS → recommend `/validate`.
8. Everything above is PASS → say so plainly; mention `/generate` (always a
   full replace) as the loop-back point if the user has since changed their
   input documents.

Report the full set of checks from both commands (grouped: input, then
connectivity/database, then generation/review/execution/validation) followed
by the one recommendation from the rule above — don't bury the
recommendation at the end of a long wall of text.
