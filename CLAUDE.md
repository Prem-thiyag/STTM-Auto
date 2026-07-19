# Project instructions for Claude Code

These apply to every contributor's Claude Code session in this repo — not
just one person's. If you're a fresh session picking this up, read this
file before touching git or GitHub.

## Hard rule: never run git or GitHub-mutating commands yourself

Claude must never execute a command that changes git history or remote
GitHub state. This includes, but isn't limited to:

- `git add`, `git commit`, `git push`, `git pull`, `git fetch` combined with
  branch deletion, `git rebase`, `git merge`, `git checkout -b` / any branch
  creation, `git reset`, `git stash`
- `gh pr create`, `gh pr merge`, `gh issue close`, `gh issue comment`, or any
  other `gh` call that mutates GitHub state (opens/closes/comments/merges)

Instead: **print the exact command(s) for the user to copy, run themselves,
and report the result back.** This holds even if the user approved a
similar action earlier in the same session — always print, never run, for
anything in the list above. Ask which of you is running it if it's
ambiguous who owns that step.

**Read-only inspection is fine to run directly** — it doesn't change any
state: `git status`, `git log`, `git diff`, `git branch --show-current`,
`gh issue view`, `gh pr view`, and `gh api` GET calls (e.g. reading issue
metadata or downloading an issue's attachment files into `input/` — that's
a plain filesystem write, not a git action).

This rule is about Claude's own live, ad hoc actions in a session — it does
not forbid the two of you from authoring a reviewed, static GitHub Actions
workflow that performs some of these steps server-side. A workflow file you
both read and merged once is a different trust boundary than Claude
improvising a mutation mid-session.

## Hard rule: code fixes found anywhere need explicit approval, presented as a choice

If *any* work — a ticket's pipeline run, building tooling, anything else —
surfaces an actual bug in the tool itself (`.claude/skills/**` or
`engine/**`, not a ticket's own input documents), Claude must stop and
describe it before touching anything: what's broken, why, and what a fix
would concretely involve. Never fix-then-report, even when the fix looks
obviously correct and small.

Don't just stop and leave it hanging, either. Always lay out the concrete
options for how to proceed (fix it now, fix it later and work around it for
now, skip it entirely, etc.) so there's something to actually choose
between — not an open-ended "what do you want to do?"

## Hard rule: ask before raising a PR — `gh` command or GitHub UI

When a ticket's branch is ready to go up for review, always ask the user
whether they want to raise the PR via `gh pr create` (Claude prints the exact
command, per the rule above — never runs it) or via the GitHub web UI. If they
choose the UI, give them the title and body text to paste in, not a command.
Don't default to either option without asking.

## Repo orientation

- [ARCHITECTURE.md](ARCHITECTURE.md) — the generator's design (ADR-001).
- [ONBOARDING.md](ONBOARDING.md) — first-time setup.
- [WORKFLOW.md](WORKFLOW.md) — day-to-day git/branching practice for the two
  of you.
