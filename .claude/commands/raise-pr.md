---
description: Build the PR title/body for a finished branch and ask whether to raise it via `gh pr create` or the GitHub UI -- per CLAUDE.md's hard rule, never opens the PR itself.
---

Argument (ticket number): `$ARGUMENTS`. Only relevant for an execution/*
ticket PR -- see step 0.

## 0. Ask what kind of PR this is -- always ask, never assume

Use `AskUserQuestion`: is this an **execution/\* ticket PR** (linked GitHub
issue, `execution/<id>-<slug>` branch) or a **develop/\* general PR** (no
linked issue, `develop/<slug>` branch)?

This decides the rest of the command:

- **execution/\*** -- if `$ARGUMENTS` is empty, ask which issue number.
  Everything in step 1/2 below applies as written.
- **develop/\*** -- skip the issue lookup and the session/event_log lookup
  entirely. There's no `Closes #<number>`. Build the summary instead from:
  ```
  git log origin/main..HEAD --oneline
  git diff --stat origin/main..HEAD
  ```
  Title: ask the user for a short one-line title (don't invent one from the
  branch name alone). Body summary: a plain-language rollup of what the
  commit log and diff stat actually show -- don't editorialize beyond what's
  there.

## 1. Gather what's needed (all read-only, execution/* only)

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

## 2. Check the branch is actually pushed

```
git status -sb
```

Look at the tracking line:

- No upstream configured (`## <branch>` with no `...origin/<branch>`) --
  print `git push -u origin <branch>` for the user to run first.
- Upstream configured but local is ahead (`ahead N`) -- print
  `git push` for the user to run first.
- Already in sync -- say so, no action needed.

Either way, this is print-only, per `CLAUDE.md`'s hard rule -- never run the
push yourself. Wait for the user to confirm they've pushed (or already were
in sync) before moving on to step 4.

## 3. Build the PR content

**execution/\* ticket PR** -- matching `.github/PULL_REQUEST_TEMPLATE.md`'s
shape:

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

**develop/\* general PR** -- no `Closes #` line, no ticket-artifact section:

```
## Summary

<plain-language rollup of the commits and changed files from step 0>

---

## Additional Notes

- No linked issue -- general develop/* branch PR.
```

## 4. Ask how to raise it, and in what shell -- always ask, never assume

Use `AskUserQuestion` (one call, both questions): (a) `gh pr create` command,
or the GitHub UI? (b) if the `gh` command -- PowerShell or Bash syntax?

- **`gh` command, Bash** -- print the exact command for the user to copy and
  run themselves (never run it yourself, per `CLAUDE.md`'s hard rule):
  ```
  gh pr create --base main --head <branch> --title "<title>" --body "$(cat <<'EOF'
  <body>
  EOF
  )"
  ```
- **`gh` command, PowerShell** -- PowerShell has no heredoc syntax; use a
  here-string written to a temp file, then `--body-file`:
  ```
  @'
  <body>
  '@ | Set-Content -Path pr_body.md
  gh pr create --base main --head <branch> --title "<title>" --body-file pr_body.md
  Remove-Item pr_body.md
  ```
- **GitHub UI** -- print just the title and body text block, ready to paste
  into the "Open a pull request" form. Mention that GitHub will pre-load
  `PULL_REQUEST_TEMPLATE.md`'s skeleton automatically; they should replace
  it with this generated content rather than merge the two.

## Report

Whichever path they chose, that's the entire output -- don't also summarize
what the command/text "will do." Nothing here touches git or GitHub state
itself.
