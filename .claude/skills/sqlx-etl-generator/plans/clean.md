# Plan: Clean

## Purpose

The `Execute` plan's mirror image, for teardown. Reads
`metadata/cleanup/cleanup_manifest.json`, shows the user one object's cleanup
command at a time, waits for confirmation, appends to
`metadata/cleanup/cleanup_log.json`. Nothing more.

## What Clean never does

- Never runs a command itself.
- Never touches `bootstrap/manifest.json` or anything under `bootstrap/` — that's
  the demo/test environment's own inventory, a deliberately separate file from
  `metadata/cleanup/cleanup_manifest.json` (see `specialists/artifact-generator.md`
  §3 and §5). Cleaning the pipeline's run artifacts must never risk tearing down
  the environment scaffolding bootstrap set up. If the user wants to reset the
  bootstrap environment itself, point them at `bootstrap/reset/*.sql` and
  `bootstrap/README.md` — those are run manually too, but they are not this
  plan's concern.
- Never infers what needs cleaning — only what
  `metadata/cleanup/cleanup_manifest.json` lists.
- Never regenerates or modifies metadata.

## Preconditions

`metadata/cleanup/cleanup_manifest.json` must exist. If it doesn't, tell the user
to run `Generate`.

## Process, per invocation

1. Load `metadata/cleanup/cleanup_manifest.json` and
   `metadata/cleanup/cleanup_log.json` (treat a missing log file as
   `{"entries": []}`).
2. Find the first object in `objects[]` not yet `confirmed` in the log.
3. If none remain, tell the user everything in the manifest has been handled.
4. Otherwise, print **exactly one** object: its `database`, `object`, `type`, and
   the full `command` string, verbatim.
5. Wait for the user to say they ran it (or want to skip it).
6. Append one entry to `metadata/cleanup/cleanup_log.json`
   (`{object, confirmed_at: <now, ISO8601>, confirmed_by: "user", status:
   "confirmed"|"skipped"}`) and stop.
