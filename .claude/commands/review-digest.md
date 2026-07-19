---
description: Reason across the latest docs/collated/*.md digest and propose what's actually worth fixing -- triage, not auto-fix.
---

Digest path: `$ARGUMENTS`. If empty, use the most recent file in
`docs/collated/` (sorted by filename, which is dated).

This is the reasoning half of the feedback cadence -- `tool/collate_feedback.py`
only ever aggregates, it never concludes anything. That judgment call happens
here, and only here.

## 1. Read the digest

It's a compiled set of every ticket's `docs/session/**/*_feedback.md` — full
section content, not just the summary table. Read every ticket's "design
gaps"/"friction" sections in full, not just the counts.

## 2. Triage, don't just summarize

For each distinct issue across all tickets in the digest, decide:

- **Recurring** — the same or a closely related problem shows up in more
  than one ticket. These are the highest-value candidates: a one-off
  friction is a data point, a recurring one is a pattern.
- **High-consequence, even if seen once** — something that silently produces
  wrong output (a false PASS/FAIL, a wrong value) outweighs something that's
  just annoying to work around.
- **Already worked around, still open** — the session doc resolved it for
  that one ticket (e.g. a manual `VARCHAR` widen) but the underlying gap in
  the skill/engine is still there for the next ticket to hit again.
- **Genuinely one-off** — specific to that ticket's input documents, not the
  tool. Note it, but don't recommend acting on it.

## 3. Present a short, ranked list — not a wall of text

For each candidate worth actually fixing: what it is, which ticket(s)
surfaced it, why it's worth fixing now rather than filed away, and a
concrete proposed change (file, function, what would change).

## 4. Get explicit approval before touching anything

Per `CLAUDE.md`'s hard rule, any code fix to `.claude/skills/**` or
`engine/**` needs the user's explicit go-ahead first. This command's job
ends at the ranked list and proposed changes -- present it, then wait. Don't
start editing files as part of running this command.
