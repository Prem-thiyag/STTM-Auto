# Workflow

Day-to-day git/branching practice for the two of you. [`CLAUDE.md`](CLAUDE.md)
covers the hard rules (Claude never runs a git/`gh` mutation itself, always
prints the command) — read that first if you haven't. This document is the
"what to actually type, in what order" companion to it.

## Branch map

| Branch | Purpose | Protection |
|---|---|---|
| `main` | Always stable. Every ticket lands here via PR. | PR + 1 approval required (from someone other than the pusher), stale approvals dismissed on new commits, conversations must resolve, linear history only (no merge commits), no force push, no deletion — enforced even for admins. |
| `execution/<id>-<slug>` | One per execution ticket, created by `/start-ticket`. | Deliberately unprotected — needs force-push (for rebasing onto `main`) and deletion (cleanup after merge) to stay possible. |
| `develop/*` | Free-push personal namespace for non-ticket work (exploring, quick fixes, anything that isn't a formal execution ticket). | Unprotected, exempt from the branch-naming ruleset. |

A repo-level ruleset blocks creating any branch that isn't `main`,
`execution/**`, or `develop/**` — see the ruleset itself for the exact
config (Settings → Rules → Rulesets).

## The ticket lifecycle

```
/start-ticket <issue-number>     # fetch issue + attachments, classify into input/,
                                  # print the branch-creation command (you run it)
  ↓
(do the work: /generate → /review → /seed → /execute → /validate)
  ↓
/finish-ticket <issue-number>    # turns real execution/validate telemetry into
                                  # docs/event_log/<year>/<Q>/ISSUE-<id>_..._log.json
  ↓
write docs/session/<year>/<Q>/ISSUE-<id>_..._feedback.md
  # -- only if there's something worth telling the repo owner (a bug fixed,
  # a design gap, a friction point). Narrative, judgment-based -- not every
  # ticket needs one, unlike the event log, which always gets written.
  ↓
/raise-pr <issue-number>        # builds the PR title/body, asks gh-command
                                  # vs. GitHub UI, never opens the PR itself
  ↓
review by the other person → squash-merge → branch auto-deleted
```

Code fixes to `.claude/skills/**` or `engine/**` discovered mid-run need your
explicit approval before Claude applies them (`CLAUDE.md`'s rule) — Claude
should stop and describe the bug + fix first, not fix-then-report.

## Daily scenarios

**Start of day**, before touching anything:
```
git checkout main
git fetch origin
git pull --ff-only origin main
```

**Starting a new ticket** — always branch off freshly-pulled `main`; this is
what `/start-ticket` prints for you to run:
```
git checkout -b execution/<id>-<slug>
```

**Mid-day, `main` has moved** (the other person merged a PR while you were
still working):
```
git fetch origin
git checkout main
git pull --ff-only origin main
git checkout execution/<id>-<slug>
git rebase main
```
Resolve any conflicts locally, right here — don't defer this to merge time.

**End of day, before pushing:**
```
git fetch origin
```
If `main` moved since you last rebased, rebase again (steps above) first.
Then:
```
git push --force-with-lease origin execution/<id>-<slug>
```
`--force-with-lease` only ever targets your *own* ticket branch — never
`main`, which rejects force pushes outright anyway. If you didn't rebase
(just new commits on top of what's already pushed), a plain `git push`
is enough; no need to force anything.

**Both of you on ticket branches simultaneously** — this is just the
mid-day-stale scenario applied at merge time: whoever's PR merges to `main`
first "wins," the other rebases onto the new `main` (steps above) before
their own PR merges.

**Abandoning a ticket branch** — no ceremony, nothing was ever merged to
`main`:
```
git branch -D execution/<id>-<slug>
git push origin --delete execution/<id>-<slug>
```

**Merge strategy:** squash-merge on every PR — `main`'s required "linear
history" setting allows either squash- or rebase-merge, but squash keeps one
clean commit per ticket regardless of how messy the WIP history on the
ticket branch got. Delete the branch on merge (GitHub's auto-delete-on-merge
setting handles this).

## Recovery playbook

**Committed directly to `main` by mistake** (branch protection rejects the
push — `! [remote rejected] main -> main (protected branch hook declined)`):
```
git log origin/main..HEAD --oneline   # see exactly what's stuck on local main
git branch <branch-name>              # point a new branch at the same commit(s)
git push -u origin <branch-name>
git checkout main
git reset --hard origin/main          # safe -- the commit already lives on <branch-name>
git checkout <branch-name>
```
Then open the PR from `<branch-name>` instead of `main`.

**Committed the wrong files** (e.g. 4 files instead of 1, not yet pushed):
```
git reset --soft HEAD~1   # undo the commit, keep every file's changes staged
git reset                 # unstage everything
git add <the-one-file>
git commit -m "..."
```
The other files stay as uncommitted changes, ready whenever you actually
want them.

## Background automation (not per-ticket)

Two scheduled/triggered pieces that run independently of any single ticket:

- **`.github/workflows/collate-feedback.yml`** — twice a week, gathers every
  `docs/session/**/*_feedback.md` into one dated digest in `docs/collated/`
  via `tool/collate_feedback.py`, and opens a PR with it. Deterministic
  aggregation only — deciding what to actually change based on the digest is
  a separate step (feed it into a Claude Code session).
- **`.github/workflows/ticket-intake.yml`** — comments on a new
  `execution`-labeled issue if its attachments look incomplete (heuristic,
  extension/count-only check via `tool/check_ticket_attachments.py`) —
  before anyone's opened Claude Code at all.

Both are static, reviewed CI jobs — a different trust boundary from Claude's
own live git/`gh` actions, per `CLAUDE.md`'s carve-out.
