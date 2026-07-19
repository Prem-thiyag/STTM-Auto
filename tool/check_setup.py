#!/usr/bin/env python3
"""Stdlib-only pre-flight check: can commands actually run right now?

Deliberately imports nothing beyond the standard library, so it can report
"a dependency is missing" without itself crashing on the very import it's
checking for. Every .claude/commands/*.md that touches Python or Postgres
runs this first and stops with a plain "/setup" pointer if anything's
missing, rather than surfacing a confusing ImportError three layers deep.

Usage:
    python tool/check_setup.py

Exit codes:
    0  every required package is importable, and a connection config exists
    1  something's missing -- printed plainly, with the fix
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# import name -> what it's actually called in requirements.txt, for a readable message
REQUIRED_PACKAGES = {
    "psycopg2": "psycopg2-binary",
    "dotenv": "python-dotenv",
    "jinja2": "jinja2",
    "jsonschema": "jsonschema",
    "openpyxl": "openpyxl",
}


def main() -> int:
    problems = []

    missing = [dist for mod, dist in REQUIRED_PACKAGES.items() if importlib.util.find_spec(mod) is None]
    if missing:
        problems.append(
            f"Missing Python package(s): {', '.join(missing)}. Run `/setup` (or "
            f"`python tool/setup_env.py`), then make sure this shell/session is actually "
            f"using that venv's python (e.g. `venv\\Scripts\\activate` on Windows)."
        )

    if not (REPO_ROOT / ".env").exists() and not (REPO_ROOT / ".mcp.json").exists():
        problems.append(
            "Neither .env nor .mcp.json exists -- no Postgres connection details "
            "configured yet. Copy .env.example to .env and fill in your actual "
            "PGHOST/PGPORT/PGUSER/PGPASSWORD (see ONBOARDING.md SS2)."
        )

    if not problems:
        print("[OK] setup looks complete -- dependencies importable, connection config present.")
        return 0

    print("[SETUP INCOMPLETE]")
    for p in problems:
        print(f"- {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
