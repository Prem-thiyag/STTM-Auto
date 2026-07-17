"""
Append-only execution logging.

Deliberately writes to a file OWNED BY THE ENGINE --
`metadata/execution/engine_execution_log.json` -- not the skill's
`metadata/execution/execution_log.json`. That file already has an owner (the
sqlx-etl-generator skill's Execute plan, per ARCHITECTURE.md's ownership
table) and a fixed, much smaller shape: one entry per human confirmation that
a command was run manually. This engine's log records the actual,
machine-observed telemetry of a real automated run -- start/end time,
duration, rows affected, a SQL hash, an error message -- which is a different
artifact with a different owner. Writing both to the same file would violate
the one-owner-per-artifact rule the skill's compliance audit specifically
checked for; keeping them separate means running the engine can never
corrupt or be confused with the skill's own human-confirmation record.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from engine.models import ExecutionRecord


class ExecutionLogger:
    """Appends ExecutionRecord entries to a JSON file, one record per call to
    `record()`. The file is read-modify-written as a whole on each call
    (append-only in effect, not in mechanism) -- there is no expectation of
    concurrent writers, since a single Engine run is a single process
    executing steps strictly in sequence."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self._lock = Lock()

    def record(self, entry: ExecutionRecord) -> None:
        with self._lock:
            data = self._read()
            data["entries"].append(self._serialize(entry))
            self._write(data)

    def read_all(self) -> list[dict]:
        return self._read()["entries"]

    def _read(self) -> dict:
        if not self.log_path.exists():
            return {"entries": []}
        raw = self.log_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {"entries": []}
        return json.loads(raw)

    def _write(self, data: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")

    @staticmethod
    def _serialize(entry: ExecutionRecord) -> dict:
        return {
            "table": entry.table,
            "stage": entry.stage.value,
            "start_time": entry.start_time,
            "end_time": entry.end_time,
            "duration_seconds": entry.duration_seconds,
            "status": entry.status.value,
            "rows_affected": entry.rows_affected,
            "sql_hash": entry.sql_hash,
            "error_message": entry.error_message,
        }
