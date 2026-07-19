#!/usr/bin/env python3
"""Heuristic, extension/count-only check of a ticket's attachments.

Not a real classifier -- final, content-based classification of which
attachment is which of the 5 required documents happens in /start-ticket (a
Claude Code command, since that genuinely requires reading each file). This
script only runs in CI, before any human opens Claude Code, to catch the
obvious case (wrong count, no workbook) early. It never looks inside any
attachment, only at the issue body's markdown links.

Usage:
    python tool/check_ticket_attachments.py <issue_body.md>

Exit codes:
    0  attachment counts look plausible, nothing to say
    1  something looks off; a comment-ready message is printed to stdout
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

NON_IMAGE_RE = re.compile(r"\[([^\]\n]+)\]\(https://github\.com/user-attachments/files/[^\)]+\)")
IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\(https://github\.com/user-attachments/assets/[^\)]+\)")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_ticket_attachments.py <issue_body.md>", file=sys.stderr)
        return 2
    body = Path(sys.argv[1]).read_text(encoding="utf-8")

    files = NON_IMAGE_RE.findall(body)
    images = IMAGE_RE.findall(body)
    xlsx = [f for f in files if f.lower().endswith(".xlsx")]
    others = [f for f in files if not f.lower().endswith(".xlsx")]

    problems = []
    if len(xlsx) == 0:
        problems.append("no `.xlsx` file found -- the STTM workbook (`sttm.xlsx`) is required.")
    elif len(xlsx) > 1:
        problems.append(f"found {len(xlsx)} `.xlsx` files ({', '.join(xlsx)}) -- unclear which is the STTM workbook.")
    if len(others) < 4:
        problems.append(
            f"found {len(others)} non-workbook attachment(s), expected at least 4 "
            "(source schema, target schema, UDF reference, folder hierarchy)."
        )

    if not problems:
        return 0

    print("**Attachment check** (automated, heuristic -- not a real classification):\n")
    for p in problems:
        print(f"- {p}")
    print(
        f"\nFound {len(files)} non-image attachment(s) total"
        + (f" and {len(images)} image attachment(s)" if images else "")
        + ". This check only counts files by extension -- it doesn't look inside them. "
        "Final classification happens locally via `/start-ticket`, which reads each "
        "attachment's actual content. If the 5 required documents are genuinely all "
        "here under different names/counts than expected, this comment can be ignored."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
