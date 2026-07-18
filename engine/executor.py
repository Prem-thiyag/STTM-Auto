"""
The engine's orchestrator: loads a validated execution plan, and runs each
step's .sqlx file, in order, one transaction per file, stopping the instant
any step fails. See engine/README.md "Execution flow" for the full picture;
this module is intentionally thin -- planner.py owns ordering, parser.py owns
file format, database.py/postgres.py own the actual SQL execution, logger.py
owns the audit trail. Engine.run() only wires those four together.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from engine.database import DatabaseExecutor
from engine.exceptions import ExecutionFailure, ValidationError
from engine.logger import ExecutionLogger
from engine.models import ExecutionRecord, ExecutionStatus, ExecutionStep
from engine.parser import parse_sqlx
from engine.planner import ExecutionPlanner
from engine.utils import now_iso, sha256_of_text

DatabaseExecutorFactory = Callable[[str], DatabaseExecutor]

DEFAULT_LOG_RELATIVE_PATH = Path("metadata") / "execution" / "engine_execution_log.json"


@dataclass(frozen=True)
class StepOutcome:
    """What happened when Engine.run() processed one step. Returned in the
    list Engine.run() gives back on success, so a caller can inspect what
    actually ran without re-reading the log file."""

    step: ExecutionStep
    record: ExecutionRecord


class Engine:
    """Executes a generated project's SQLX pipeline against real databases.

    `database_executor_factory` is the dependency-injection seam: given a
    database name (as named in a .sqlx file's config block), it must return a
    connected-but-not-yet-transacted DatabaseExecutor for that database. In
    production this wraps PostgresExecutor; in tests it returns a
    MockDatabaseExecutor -- Engine itself never imports psycopg2 or knows
    PostgreSQL exists.
    """

    def __init__(
        self,
        project_root: Path,
        database_executor_factory: DatabaseExecutorFactory,
        logger: ExecutionLogger | None = None,
    ) -> None:
        self.project_root = project_root
        self._database_executor_factory = database_executor_factory
        self.logger = logger or ExecutionLogger(project_root / DEFAULT_LOG_RELATIVE_PATH)
        self.planner = ExecutionPlanner(project_root)

    def run(self) -> list[StepOutcome]:
        """Run every step in the execution plan, in plan order. Returns the
        list of StepOutcome for every step that succeeded. Raises
        ExecutionFailure -- after logging the failure -- on the first step
        that fails, without attempting any further step, per
        "if any stage fails, immediately stop execution"."""
        steps = self.planner.sequence()
        outcomes: list[StepOutcome] = []
        for step in steps:
            outcomes.append(self._run_step(step))
        return outcomes

    def _run_step(self, step: ExecutionStep) -> StepOutcome:
        sqlx_path = self.project_root / step.file
        sqlx_file = parse_sqlx(sqlx_path)

        # execution_plan.json's `database` and the .sqlx file's own config
        # block both carry this value (a deliberate, documented duplication --
        # see engine/README.md "Declared vs. observed database"), so a drift
        # between the two (e.g. a hand-edited plan or a stale regeneration)
        # is caught here rather than silently trusting whichever was read
        # first.
        if step.database != sqlx_file.config.database:
            raise ValidationError(
                f"step '{step.step_id}' ({step.table}.{step.stage.value}): "
                f"execution_plan.json declares database '{step.database}' but "
                f"{sqlx_path} declares '{sqlx_file.config.database}'. These must "
                f"match -- regenerate the project rather than hand-editing either file."
            )

        db = self._database_executor_factory(sqlx_file.config.database)
        start = now_iso()
        start_perf = time.perf_counter()

        db.connect()
        db.begin_transaction()
        try:
            result = db.execute(sqlx_file.sql)
        except Exception as exc:
            db.rollback()
            end = now_iso()
            duration = time.perf_counter() - start_perf
            record = ExecutionRecord(
                table=step.table,
                stage=step.stage,
                start_time=start,
                end_time=end,
                duration_seconds=duration,
                status=ExecutionStatus.FAILURE,
                rows_affected=None,
                sql_hash=sha256_of_text(sqlx_file.sql),
                error_message=str(exc),
            )
            self.logger.record(record)
            db.close()
            raise ExecutionFailure(
                f"step '{step.step_id}' ({step.table}.{step.stage.value}) failed: {exc}. "
                f"Execution stopped -- no further steps were run."
            ) from exc
        else:
            db.commit()
            end = now_iso()
            duration = time.perf_counter() - start_perf
            record = ExecutionRecord(
                table=step.table,
                stage=step.stage,
                start_time=start,
                end_time=end,
                duration_seconds=duration,
                status=ExecutionStatus.SUCCESS,
                rows_affected=result.rows_affected,
                sql_hash=sha256_of_text(sqlx_file.sql),
                error_message=None,
            )
            self.logger.record(record)
            db.close()
            return StepOutcome(step=step, record=record)


def _default_database_executor_factory() -> DatabaseExecutorFactory:
    """Builds PostgresExecutor instances with connection details resolved
    per-database at call time (see postgres.resolve_connection_config).
    This is the factory `main()` uses; tests inject their own instead."""
    from engine.postgres import PostgresExecutor, resolve_connection_config

    def factory(database: str) -> DatabaseExecutor:
        return PostgresExecutor(resolve_connection_config(database))

    return factory


def main() -> int:
    """CLI entry point: `python -m engine [project_root]` (see __main__.py).
    `project_root` defaults to `output/` relative to the current directory --
    the sqlx-etl-generator skill's default Generate output location."""
    from engine.exceptions import EngineError

    try:
        from dotenv import load_dotenv
        load_dotenv()  # repo-root .env -> os.environ, if present; never overwrites already-set vars
    except ImportError:  # pragma: no cover - exercised only when python-dotenv truly isn't installed
        pass

    project_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output")
    if not project_root.exists():
        print(f"ERROR: project root not found: {project_root}", file=sys.stderr)
        return 2

    engine = Engine(project_root, _default_database_executor_factory())
    try:
        outcomes = engine.run()
    except EngineError as exc:
        # Every exception this package raises -- ExecutionFailure,
        # ExecutionPlanError, SQLXParseError, DatabaseConnectionError,
        # ValidationError -- is a descriptive EngineError; none of them
        # should ever surface as a raw Python traceback to a CLI user.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for outcome in outcomes:
        print(
            f"OK  {outcome.step.table:<24} {outcome.step.stage.value:<8} "
            f"rows_affected={outcome.record.rows_affected}"
        )
    print(f"\n{len(outcomes)} step(s) completed successfully.")
    return 0


# Run via `python -m engine [project_root]` (engine/__main__.py), not this
# module directly -- see __main__.py's docstring for why.
