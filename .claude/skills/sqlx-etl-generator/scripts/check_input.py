#!/usr/bin/env python3
"""
Deterministic precondition check for the five documents Generate reads.

Owned jointly by Generate's Preconditions (plans/generate.md) and the
repository's /start-sttm command -- both delegate to this script instead of
re-checking or re-listing the required filenames themselves, so the list of
required documents has exactly one home: REQUIRED_INPUT_FILES below.

This script does presence/shape checks only, never semantic validation of a
markdown document's content -- classifying whether a schema doc or STTM
mapping is actually *correct* is the Schema Parser / STTM Parser / Artifact
Generator specialists' job (an LLM step), not something worth re-implementing
here. The one document with an existing deterministic parser is the STTM
workbook (parse_sttm.py); this script shells out to it (never writing
anything -- --output is omitted) to catch a structurally broken workbook
before Generate spends specialist steps on it.

Usage:
    python check_input.py [input_dir]      # default: input/

Exit codes:
    0  every required file present, non-empty, and (for the workbook)
       structurally parseable
    1  one or more required files missing or empty
    2  the STTM workbook is present but fails parse_sttm.py's own structural
       validation (its stderr is relayed, not duplicated)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# The one and only place these five filenames are declared. Every other
# consumer (plans/generate.md, .claude/commands/start-sttm.md) runs this
# script rather than re-listing them.
REQUIRED_INPUT_FILES: tuple[str, ...] = (
    "source_schema.md",
    "target_schema.md",
    "sttm.xlsx",
    "user_defined_functions.md",
    "folder_hierarchy.md",
)

_SAMPLE_HINT = "templates/sample-input/"
_PARSE_STTM = Path(__file__).parent / "parse_sttm.py"


def _check_presence(input_dir: Path) -> list[tuple[str, bool, str]]:
    """One (filename, ok, message) tuple per required file -- existence and
    non-empty only, no content interpretation."""
    results = []
    for name in REQUIRED_INPUT_FILES:
        path = input_dir / name
        if not path.exists():
            results.append((name, False, f"not found -- copy {_SAMPLE_HINT}{name} to get started"))
        elif path.stat().st_size == 0:
            results.append((name, False, "present but empty"))
        else:
            results.append((name, True, "present"))
    return results


def _check_workbook_structure(workbook_path: Path) -> tuple[bool, str]:
    """Reuses parse_sttm.py's own structural validation via subprocess (never
    imports its internals, never writes an --output file) -- one call, its
    exit code and stderr are authoritative. stdout (the full normalized JSON)
    is discarded either way; nothing here needs it and relaying it would be
    pure token waste for what's meant to be a one-line check result."""
    proc = subprocess.run(
        [sys.executable, str(_PARSE_STTM), str(workbook_path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return True, "structurally valid"
    stderr = proc.stderr.strip()
    if "openpyxl is required" in stderr:
        return False, f"{stderr} (pip install -r .claude/skills/sqlx-etl-generator/scripts/requirements.txt)"
    return False, stderr or f"parse_sttm.py exited {proc.returncode}"


def main() -> int:
    input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("input")

    presence = _check_presence(input_dir)
    for name, ok, message in presence:
        print(f"[{'OK' if ok else 'MISSING'}] {name} -- {message}")

    missing = [name for name, ok, _ in presence if not ok]
    if missing:
        print(f"\n{len(missing)} of {len(REQUIRED_INPUT_FILES)} required file(s) missing or empty.", file=sys.stderr)
        return 1

    workbook_ok, workbook_detail = _check_workbook_structure(input_dir / "sttm.xlsx")
    print(f"[{'OK' if workbook_ok else 'INVALID'}] sttm.xlsx structure -- {workbook_detail}")
    if not workbook_ok:
        return 2

    print("\nAll required input documents present and structurally valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
