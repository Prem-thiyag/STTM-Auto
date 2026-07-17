#!/usr/bin/env python3
"""
Generic JSON Schema validator wrapper, shared by every specialist and by the Review plan.

Every metadata artifact this skill produces has a corresponding schema in schemas/. Rather
than have each specialist or plan re-implement validation (or worse, have an LLM step
eyeball a JSON file for "correctness"), they all shell out to this one script. This is
the concrete mechanism behind ADR-001's "no downstream specialist may invent its own
rules" and "Review validates against generated specifications instead of inventing them."

Usage:
    python validate_schema.py <instance.json> <schema.json>
    python validate_schema.py <instance_dir> <schema.json> --glob "*.buildspec.json"

Exit codes:
    0  every instance is valid
    1  one or more instances failed validation (details on stderr)
    2  usage / file-not-found error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema is required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(2)


def validate_one(instance_path: Path, schema: dict) -> list[str]:
    try:
        instance = json.loads(instance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{instance_path}: not valid JSON ({exc})"]

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    return [f"{instance_path}: {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance_path", type=Path, help="A JSON file, or a directory with --glob")
    parser.add_argument("schema_path", type=Path)
    parser.add_argument("--glob", default=None, help="Glob pattern when instance_path is a directory")
    args = parser.parse_args()

    if not args.schema_path.exists():
        print(f"ERROR: schema not found: {args.schema_path}", file=sys.stderr)
        return 2
    schema = json.loads(args.schema_path.read_text(encoding="utf-8"))

    if args.instance_path.is_dir():
        if not args.glob:
            print("ERROR: --glob is required when instance_path is a directory", file=sys.stderr)
            return 2
        instances = sorted(args.instance_path.glob(args.glob))
        if not instances:
            print(f"ERROR: no files matched {args.glob} in {args.instance_path}", file=sys.stderr)
            return 2
    else:
        if not args.instance_path.exists():
            print(f"ERROR: instance not found: {args.instance_path}", file=sys.stderr)
            return 2
        instances = [args.instance_path]

    all_errors: list[str] = []
    for instance_path in instances:
        all_errors.extend(validate_one(instance_path, schema))

    if all_errors:
        print("INVALID:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"OK: {len(instances)} instance(s) valid against {args.schema_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
