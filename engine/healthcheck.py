"""
Read-only project status: how far along a generated project actually is,
without assuming a fixed pipeline stage. Backs the repository's /start-sttm
command the same way dbadmin.py backs /seed and /execute, and validate.py
backs /validate -- a thin CLI over primitives that already exist elsewhere in
this package.

**Never reads input/ or the five source documents** (source_schema.md,
target_schema.md, the STTM workbook, user_defined_functions.md,
folder_hierarchy.md) -- that boundary is already documented in this
package's own README ("Nothing in this package... reads a source
document") and this module doesn't cross it either. Everything checked here
is either a live Postgres property (connectivity, which databases exist) or
an artifact already written under a generated project's own metadata/ --
the same territory validate.py already reads.

Which databases to check for existence is **not** a hardcoded list. A
project's actual database names come from wherever its source/target schema
documents declared them (see the skill's docs/ASSUMPTIONS.md "Database
schema/namespace is a resolved field... never guessed") -- nothing is
really fixed to source_db/intermediate_db/target_db. execution_plan.json is
already the one place that resolved set is recorded, and engine.planner
already validates it, so this module reads the distinct `database` values
off ExecutionPlanner(project_root).sequence() rather than assuming a fixed
tuple. dbadmin.MANAGED_DATABASES is deliberately not reused here -- it's
dbadmin.py's own fixed-name behavior for /seed, unrelated to what a given
generated project actually declares.

Every check always resolves to a status, never raises past this module --
an early-stage clone (nothing generated yet, Postgres unreachable) is a
legitimate state with WARNs everywhere, not a script failure. Exit code is
therefore always 0; the CLI's job is to report, not to gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine.dbadmin import admin_connection
from engine.exceptions import EngineError, ExecutionPlanError
from engine.planner import ExecutionPlanner
from engine.postgres import resolve_connection_config
from engine.validate import Check

try:
    import psycopg2
except ImportError:  # pragma: no cover - exercised only when the driver truly isn't installed
    psycopg2 = None  # type: ignore[assignment]


def check_connectivity() -> tuple[Check, object]:
    """Returns the connectivity Check plus the resolved config (or None) so
    later checks can reuse the same connection details instead of
    re-resolving them."""
    try:
        config = resolve_connection_config("postgres")
    except EngineError as exc:
        return Check("connectivity", "database", "FAIL", str(exc)), None

    if psycopg2 is None:
        return (
            Check("connectivity", "database", "FAIL",
                  "psycopg2 not installed -- pip install -r engine/requirements.txt"),
            None,
        )

    try:
        conn = admin_connection(config)
        conn.close()
    except EngineError as exc:
        return Check("connectivity", "database", "FAIL", str(exc)), None
    except psycopg2.OperationalError as exc:
        return Check("connectivity", "database", "FAIL", f"could not connect: {exc}"), None

    return Check("connectivity", "database", "PASS", f"connected to {config.host}:{config.port}"), config


def check_managed_databases(project_root: Path, config: object) -> list[Check]:
    """Which databases this specific project declares, read from its own
    execution_plan.json (see module docstring) -- skipped entirely if that
    file doesn't exist yet (nothing has been generated, so there's no known
    database set to check)."""
    plan_path = project_root / "metadata" / "execution" / "execution_plan.json"
    if not plan_path.exists():
        return []

    try:
        steps = ExecutionPlanner(project_root).sequence()
    except ExecutionPlanError as exc:
        return [Check("execution-plan", "database", "FAIL", str(exc))]

    databases = sorted({step.database for step in steps})
    if config is None:
        return [Check(f"database-{db}", "database", "WARN", "cannot check -- no Postgres connectivity")
                for db in databases]

    checks: list[Check] = []
    try:
        conn = admin_connection(config)
        try:
            with conn.cursor() as cur:
                for db in databases:
                    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db,))
                    exists = cur.fetchone() is not None
                    checks.append(Check(
                        f"database-{db}", "database",
                        "PASS" if exists else "WARN",
                        f"{db} exists" if exists else f"{db} not yet created -- run /seed",
                    ))
        finally:
            conn.close()
    except (EngineError, psycopg2.OperationalError) as exc:  # pragma: no cover - defensive
        checks.append(Check("database-list", "database", "FAIL", f"could not query pg_database: {exc}"))
    return checks


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def check_generation(project_root: Path) -> Check:
    manifest = project_root / "metadata" / "manifest.json"
    if not manifest.exists():
        return Check("generation", "generation", "WARN", "not yet run -- /generate has not produced output/")
    return Check("generation", "generation", "PASS", f"{manifest} present")


def check_review(project_root: Path) -> Check:
    data = _read_json(project_root / "metadata" / "review" / "review_report.json")
    if data is None:
        return Check("review", "review", "WARN", "not yet run")
    status = data.get("status", "WARN")
    return Check("review", "review", status, f"review_report.json status = {status}")


def check_execution(project_root: Path) -> Check:
    data = _read_json(project_root / "metadata" / "execution" / "engine_execution_log.json")
    if data is None:
        return Check("execution", "execution", "WARN", "not yet run")
    entries = data.get("entries", [])
    if not entries:
        return Check("execution", "execution", "WARN", "engine_execution_log.json has no entries yet")
    if any(e.get("status") == "failure" for e in entries):
        failed = next(e for e in entries if e.get("status") == "failure")
        return Check("execution", "execution", "FAIL",
                     f"{failed.get('table')}.{failed.get('stage')} failed: {failed.get('error_message')}")
    return Check("execution", "execution", "PASS", f"{len(entries)} step(s) completed successfully")


def check_validation(project_root: Path) -> Check:
    data = _read_json(project_root / "metadata" / "validate" / "validation_report.json")
    if data is None:
        return Check("validation", "validation", "WARN", "not yet run")
    status = data.get("status", "WARN")
    return Check("validation", "validation", status, f"validation_report.json status = {status}")


def run(project_root: Path) -> list[Check]:
    connectivity_check, config = check_connectivity()
    checks = [connectivity_check]
    checks += check_managed_databases(project_root, config)
    checks.append(check_generation(project_root))
    checks.append(check_review(project_root))
    checks.append(check_execution(project_root))
    checks.append(check_validation(project_root))
    return checks


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()  # repo-root .env -> os.environ, if present; never overwrites already-set vars
    except ImportError:  # pragma: no cover - exercised only when python-dotenv truly isn't installed
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", nargs="?", default="output", type=Path)
    args = parser.parse_args()

    for check in run(args.project_root):
        print(f"[{check.status}] {check.id} ({check.category}) -- {check.detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
