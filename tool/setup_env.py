#!/usr/bin/env python3
"""One-time local dev environment bootstrap.

Creates ./venv if it doesn't already exist, and installs every Python
dependency this repo needs INTO that venv -- never into the system/global
Python, and never by assuming a venv is already active. If Node is
available, also runs the one-time `npm install -g envmcp` step; skipped
cleanly (not an error) if Node isn't installed, since it's only needed for
the optional Postgres MCP path (see ONBOARDING.md SS2).

Usage:
    python tool/setup_env.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / "venv"

PIP_REQUIREMENTS = [
    REPO_ROOT / "engine" / "requirements.txt",
    REPO_ROOT / ".claude" / "skills" / "sqlx-etl-generator" / "scripts" / "requirements.txt",
]


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(*args: str) -> None:
    print(f"$ {' '.join(args)}")
    subprocess.run(args, check=True)


def main() -> int:
    if not VENV_DIR.exists():
        print(f"No venv at {VENV_DIR} -- creating one.")
        run(sys.executable, "-m", "venv", str(VENV_DIR))
    else:
        print(f"Reusing existing venv at {VENV_DIR}.")

    py = str(venv_python())
    for req in PIP_REQUIREMENTS:
        if not req.exists():
            print(f"warning: {req} not found, skipping", file=sys.stderr)
            continue
        run(py, "-m", "pip", "install", "-r", str(req))
    run(py, "-m", "pip", "install", "pytest")  # matches engine/README.md "Testing" + tests.yml

    if shutil.which("npm"):
        print("Node found -- installing envmcp globally (one-time, per ONBOARDING.md SS2).")
        # Windows can't exec npm (a .cmd shim) directly via subprocess without going
        # through cmd.exe -- same reason .mcp.json itself wraps its own npx call in
        # `cmd /c` rather than invoking npx bare.
        npm_cmd = ["cmd", "/c", "npm", "install", "-g", "envmcp"] if sys.platform == "win32" \
            else ["npm", "install", "-g", "envmcp"]
        subprocess.run(npm_cmd, check=False)
    else:
        print(
            "Node/npm not found -- skipping envmcp install. Only needed if you use the "
            "Postgres MCP server; see ONBOARDING.md SS2 if/when you do."
        )

    activate = r"venv\Scripts\activate" if sys.platform == "win32" else "source venv/bin/activate"
    print(f"\nDone. Activate the venv with: {activate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
