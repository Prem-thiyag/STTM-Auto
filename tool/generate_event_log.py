#!/usr/bin/env python3
"""Turn a ticket's real execution/validation telemetry into a committed event log.

Deterministic aggregation only -- no reasoning, no fabrication. Reads the two
JSON artifacts the engine itself already wrote for this run:

    output/metadata/execution/engine_execution_log.json  (engine/logger.py)
    output/metadata/validate/validation_report.json      (engine/validate.py)

and writes one combined, durable record to
docs/event_log/<year>/<quarter>/ISSUE-<ticket>_<date>_<slug>_log.json --
the only copy of this telemetry that survives past the next /generate or
/clean, since output/ is gitignored and ephemeral.

This does not write docs/session/**/*_feedback.md -- that's a narrative,
judgment-based writeup (bugs found, design gaps) and stays a human/Claude
task. This script only ever relays what the engine already recorded.

Usage:
    python tool/generate_event_log.py --ticket 2 --branch execution/2-healthcare-etl --slug healthcare-etl
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path


def quarter_of(date: datetime.date) -> str:
    return f"Q{(date.month - 1) // 3 + 1}"


def load_json(path: Path, hint: str) -> dict:
    if not path.exists():
        print(f"error: {path} does not exist -- {hint}", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_execution(execution_log: dict) -> dict:
    entries = execution_log.get("entries", [])
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {"step_count": len(entries), "status_counts": counts}


def summarize_validation(validation_report: dict) -> dict:
    counts: dict[str, int] = {}
    for check in validation_report.get("checks", []):
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    return {"check_count": len(validation_report.get("checks", [])), "status_counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket", required=True, type=int)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    parser.add_argument("--execution-log", type=Path,
                         default=Path("output/metadata/execution/engine_execution_log.json"))
    parser.add_argument("--validation-report", type=Path,
                         default=Path("output/metadata/validate/validation_report.json"))
    parser.add_argument("--narrative-doc", default=None,
                         help="repo-relative path to this ticket's docs/session/**/*_feedback.md, if it exists")
    parser.add_argument("--output-dir", type=Path, default=Path("docs/event_log"))
    args = parser.parse_args()

    execution_log = load_json(args.execution_log, "run /execute first")
    validation_report = load_json(args.validation_report, "run /validate first")

    date = datetime.date.fromisoformat(args.date)
    year, quarter = str(date.year), quarter_of(date)

    record = {
        "ticket": args.ticket,
        "branch": args.branch,
        "date": args.date,
        "narrative_doc": args.narrative_doc,
        "execution": {
            "source": args.execution_log.as_posix(),
            "summary": summarize_execution(execution_log),
            "entries": execution_log.get("entries", []),
        },
        "validation": {
            "source": args.validation_report.as_posix(),
            "validated_at": validation_report.get("validated_at"),
            "status": validation_report.get("status"),
            "summary": summarize_validation(validation_report),
            "checks": validation_report.get("checks", []),
        },
    }

    out_dir = args.output_dir / year / quarter
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ISSUE-{args.ticket}_{args.date}_{args.slug}_log.json"
    out_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
