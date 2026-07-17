"""
Small, generic helpers shared across the engine. Nothing here is SQLX-,
PostgreSQL-, or plan-specific -- that logic lives in parser.py, postgres.py,
and planner.py respectively. Keeping this module free of domain logic is what
lets every other module import from it without risking a circular import.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def now_iso() -> str:
    """Current UTC time, ISO 8601, matching every timestamp format already
    used elsewhere in this project (e.g. YYYY-MM-DDTHH:MM:SSZ)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_of_text(text: str) -> str:
    """Hash of a SQL statement's exact text, recorded per execution so the
    log can prove which literal SQL ran without storing the SQL itself."""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def find_matching_brace(text: str, open_index: int) -> int:
    """Given the index of an opening `{` in `text`, return the index of its
    matching closing `}`, accounting for nested braces and braces inside
    string literals. Raises ValueError if the braces are unbalanced.

    Used by parser.py to locate the end of a config block's JSON object
    without assuming anything about its internal formatting (indentation,
    line breaks, nested objects are all fine)."""
    if text[open_index] != "{":
        raise ValueError(f"index {open_index} is not an opening brace")

    depth = 0
    in_string = False
    escape = False
    for i in range(open_index, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced braces: no matching '}' found")
