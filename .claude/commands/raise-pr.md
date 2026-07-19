---
description: Build the PR title/body for a finished ticket and ask whether to raise it via `gh pr create` or the GitHub UI -- per CLAUDE.md's hard rule, never opens the PR itself.
---

Ticket number: `$ARGUMENTS`. If empty, ask which issue number before doing
anything else.

## 1. Gather what's needed (all read-only)

```
git branch --show-current
gh issue view $ARGUMENTS --json title,number
```

Then look for this ticket's two artifacts:

```
ls docs/session/*/*/ISSUE-$ARGUMENTS_*_feedback.md 2>/dev/null
ls docs/event_log/*/*/ISSUE-$ARGUMENTS_*_log.json 2>/dev/null
```

If either is missing, don't fail outright -- tell the user `/finish-ticket`
doesn't look like it's been run yet (or the session feedback wasn't
written), and confirm they actually want to raise the PR now anyway before
continuing. Read whichever of the two *do* exist: pull the event log's
`execution.summary` and `validation.status`/`validation.summary` fields for
a factual one-line status, and the session feedback's `## Net result`
section (or similar closing section) for a short narrative bullet or two.
Never invent either if the source doc doesn't exist -- say "not written
yet" plainly instead.

## 2. Build the PR content, matching `.github/PULL_REQUEST_TEMPLATE.md`'s shape

Title: reuse the issue's own title as-is (it already carries the
`[Execution]: ` framing from the ticket template).

Body:

```
Closes #<number>

---

## Summary

<one factual line from the event log: step/check counts and overall status>

<one or two bullets from the session feedback's closing section, if it exists>

---

## Additional Notes

- Session feedback: <path, or "not written yet">
- Event log: <path, or "not written yet">
```

## 3. Ask which way to raise it -- always ask, never assume

Use `AskUserQuestion` (or just ask plainly): `gh pr create` command, or the
GitHub UI?

- **`gh` command** -- print the exact command for the user to copy and run
  themselves (never run it yourself, per `CLAUDE.md`'s hard rule):
  ```
  gh pr create --base main --head <branch> --title "<title>" --body "$(cat <<'EOF'
  <body>
  EOF
  )"
  ```
- **GitHub UI** -- print just the title and body text block, ready to paste
  into the "Open a pull request" form. Mention that GitHub will pre-load
  `PULL_REQUEST_TEMPLATE.md`'s skeleton automatically; they should replace
  it with this generated content rather than merge the two.

## Report

Whichever path they chose, that's the entire output -- don't also summarize
what the command/text "will do." Nothing here touches git or GitHub state
itself.
