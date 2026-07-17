# Plan: Execute

## Purpose

The lightest plan in this skill, deliberately. Execute has exactly one job: show
the user the next step from `metadata/execution/execution_plan.json` and wait
for them to confirm they ran it. That's the whole plan.

`execution_plan.json` itself carries no command string (see
`docs/ASSUMPTIONS.md` "`execution_plan.json` is declarative") — just
`table`, `stage`, `database`, `file`, `depends_on`. Execute formats the
display command itself, by substituting those fields into one fixed template,
`psql -d <database> -f <file>`. This is a formatting rule applied at display
time, not a value read from metadata, and it requires no judgment about *which*
command to show — if the user's environment uses something other than `psql`
(an MCP tool, a different CLI), they translate the substitution themselves;
Execute doesn't need to know or care which.

## What Execute never does

- Never runs a command itself, against any database, through MCP or otherwise.
- Never modifies SQL, a buildspec, or any metadata file other than appending to
  `metadata/execution/execution_log.json`.
- Never infers an execution order — the order is whatever
  `metadata/execution/execution_plan.json` already says.
- Never regenerates anything — if a step looks wrong, that's a `Generate` problem,
  not something Execute fixes.
- Never reasons about *why* a step exists or *whether* it's a good idea. If the
  user asks "should I run this," answer from what `review_report.json` says (pass/
  fail/warn), not from independent judgment about the SQL's correctness — that
  judgment already happened in `Generate`/`Review`.

If you catch yourself about to explain *why* a piece of generated SQL does what it
does beyond reading its header comment aloud, stop — that's `Review`'s job (or the
user reading `definitions/` themselves), not Execute's.

## Preconditions

`metadata/execution/execution_plan.json` must exist. If it doesn't, tell the user
to run `Generate`.

## Gate check (a lookup, not reasoning)

Read `metadata/review/review_report.json` if it exists.
- `status: "FAIL"` — tell the user Review failed and list why, and ask them to
  confirm they still want to proceed before showing any command. Do not refuse
  outright; the user may have already judged the failure acceptable, but they
  must say so explicitly for this session.
- `status: "WARN"` — mention it once, then proceed.
- `status: "PASS"` — proceed silently.
- File doesn't exist — tell the user Review has never been run and confirm they
  want to proceed without it.

This is a status-field lookup, not architectural reasoning — it stays inside
Execute's boundary.

## Process, per invocation

1. Load `metadata/execution/execution_plan.json` and
   `metadata/execution/execution_log.json` (treat a missing log file as
   `{"entries": []}`).
2. Find the first step (in `steps[]` order) whose `depends_on` are all already
   `confirmed` in the log, and which is not itself already `confirmed`.
3. If none remain, tell the user the plan is fully executed.
4. Otherwise, print **exactly one** step: its `table`, `stage`, `file`,
   `database`, and the display command `psql -d <database> -f <file>` built
   from those fields (see Purpose above) — ready to copy-paste, or to translate
   to the user's actual execution mechanism.
5. Wait for the user to say they ran it (or that they want to skip it).
6. Append one entry to `metadata/execution/execution_log.json`
   (`{step_id, confirmed_at: <now, ISO8601>, confirmed_by: "user", status:
   "confirmed"|"skipped"}`) and stop. Do not automatically continue to the next
   step in the same turn — the next invocation of this plan picks up from here.
