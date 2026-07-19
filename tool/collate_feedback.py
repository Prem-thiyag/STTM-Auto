#!/usr/bin/env python3
"""Collate every docs/session/**/*_feedback.md into one compiled digest.

Deterministic aggregation only -- this script does not decide what to fix.
It gathers every session feedback doc found (all tickets, all time; stateless,
re-scans everything on each run), pulls out its frontmatter and section
structure, and writes one dated digest to docs/collated/. Deciding what to
actually change based on that digest is a separate step: feed the digest
into a Claude Code session and let it reason across tickets.

Usage:
    python tool/collate_feedback.py
    python tool/collate_feedback.py --session-dir docs/session --output-dir docs/collated
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from pathlib import Path

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
H3_RE = re.compile(r"^### ", re.MULTILINE)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading '---' YAML-ish block (flat key: value pairs only) from the body."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw_fm, body = match.group(1), match.group(2)
    fields: dict[str, str] = {}
    for line in raw_fm.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, body


def split_sections(body: str) -> list[tuple[str, str]]:
    """Return [(heading, section_text)] for every '## ' heading in the doc, in order."""
    headings = list(H2_RE.finditer(body))
    sections = []
    for i, m in enumerate(headings):
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        sections.append((m.group(1).strip(), body[start:end].strip()))
    return sections


def collate(session_dir: Path) -> list[dict]:
    entries = []
    for path in sorted(session_dir.rglob("*_feedback.md")):
        text = path.read_text(encoding="utf-8")
        fields, body = parse_frontmatter(text)
        if not fields:
            print(f"warning: {path} has no frontmatter, skipping structured fields", file=sys.stderr)
        sections = split_sections(body)
        entries.append({
            "path": path,
            "ticket": fields.get("ticket", "?"),
            "date": fields.get("date", "?"),
            "branch": fields.get("branch", "?"),
            "sections": [(name, len(H3_RE.findall(text))) for name, text in sections],
            "raw_sections": sections,
        })
    return entries


def render_digest(entries: list[dict], generated_on: str, output_dir: Path) -> str:
    lines = [
        f"# Collated feedback digest — {generated_on}",
        "",
        "Deterministic aggregation of every `docs/session/**/*_feedback.md` found in the repo "
        "as of this run (stateless — always the full set, not just what's new). This digest "
        "does not draw conclusions across tickets; feed it into a Claude Code session to reason "
        "about recurring patterns and decide what to actually change.",
        "",
        "## Tickets covered",
        "",
        "| Ticket | Date | Branch | Sections (items) | Doc |",
        "|---|---|---|---|---|",
    ]
    for e in entries:
        section_summary = ", ".join(f"{name} ({count})" for name, count in e["sections"]) or "—"
        rel_path = e["path"].as_posix()
        link = Path(os.path.relpath(e["path"], start=output_dir)).as_posix()
        lines.append(f"| #{e['ticket']} | {e['date']} | `{e['branch']}` | {section_summary} | [{rel_path}]({link}) |")

    lines += ["", "---", "", "## Full content, per ticket"]
    for e in entries:
        lines.append(f"\n### Ticket #{e['ticket']} — {e['date']} (`{e['branch']}`)\n")
        for name, text in e["raw_sections"]:
            lines.append(f"#### {name}\n")
            lines.append(text)
            lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, default=Path("docs/session"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/collated"))
    args = parser.parse_args()

    if not args.session_dir.exists():
        print(f"error: {args.session_dir} does not exist", file=sys.stderr)
        return 1

    entries = collate(args.session_dir)
    if not entries:
        print(f"no *_feedback.md files found under {args.session_dir}", file=sys.stderr)
        return 0

    today = datetime.date.today().isoformat()
    digest = render_digest(entries, today, args.output_dir)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"{today}_collated-feedback.md"
    out_path.write_text(digest, encoding="utf-8")
    print(f"wrote {out_path} ({len(entries)} ticket(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
