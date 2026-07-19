# docs/

Three subdirectories, one convention tying them together. See
[`WORKFLOW.md`](../WORKFLOW.md) for the ticket lifecycle these get written
during; this file documents the naming/pairing convention itself.

## The three subdirectories

| Directory | What goes here | Written | Format |
|---|---|---|---|
| `session/` | Narrative feedback — bugs fixed, design gaps, friction points worth the repo owner's attention. | Only when there's something worth saying; not every ticket needs one. Judgment-based, human/Claude-authored. | Markdown, YAML frontmatter |
| `event_log/` | The factual record of what `/execute` and `/validate` actually did for a ticket. | Every ticket, always, via `/finish-ticket` — mechanical, `tool/generate_event_log.py` (no reasoning, no fabrication). | JSON |
| `collated/` | Periodic digest of every `session/` doc, for spotting recurring patterns across tickets. | Twice a week, via `tool/collate_feedback.py` / `.github/workflows/collate-feedback.yml`. Flat — no year/quarter split. | Markdown |

## Naming convention

`session/` and `event_log/` both partition by **year/quarter** (calendar
quarters: Q1 Jan–Mar, Q2 Apr–Jun, Q3 Jul–Sep, Q4 Oct–Dec), computed from the
ticket's own date, not the date the file happens to be written:

```
docs/session/<year>/<quarter>/ISSUE-<id>_<date>_<slug>_feedback.md
docs/event_log/<year>/<quarter>/ISSUE-<id>_<date>_<slug>_log.json
```

`<date>` and `<slug>` are always identical between a ticket's two files —
`<slug>` in particular comes straight from the ticket's branch name
(`execution/<id>-<slug>`), never recomputed independently, so the branch,
the feedback doc, and the event log always agree with each other by
construction. `collated/` stays flat: `docs/collated/<date>_collated-feedback.md`,
one per cadence run, dated by when the digest was generated (not tied to
any single ticket).

## Cross-referencing between the pair

Each file points at its counterpart, so either one is a complete entry
point:

`session/**/*_feedback.md` — YAML frontmatter:
```yaml
---
ticket: 2
branch: execution/2-healthcare-etl
date: 2026-07-18
event_log: docs/event_log/2026/Q3/ISSUE-2_2026-07-18_healthcare-etl_log.json
---
```

`event_log/**/*_log.json` — plain top-level fields:
```json
{
  "ticket": 2,
  "branch": "execution/2-healthcare-etl",
  "date": "2026-07-18",
  "narrative_doc": "docs/session/2026/Q3/ISSUE-2_2026-07-18_healthcare-etl_feedback.md",
  "execution": { "...": "..." },
  "validation": { "...": "..." }
}
```

`narrative_doc`/`event_log` is optional in both directions — an event log
can exist before its ticket's session feedback is written (or without one
ever being written, if the run was uneventful), but never point at a file
that doesn't exist; omit the field instead of guessing a future path.
