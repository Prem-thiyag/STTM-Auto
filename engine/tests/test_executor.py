import json
from pathlib import Path

import pytest

from engine.database import MockDatabaseExecutor
from engine.exceptions import ExecutionFailure, ValidationError
from engine.executor import Engine
from engine.models import ExecutionStatus


def test_full_run_against_real_generated_project_succeeds(real_output_project: Path, tmp_path: Path) -> None:
    """Runs the engine against the actual project this session generated
    from input/ (real schema, real STTM-derived buildspecs, real rendered
    SQLX with the config block) using a MockDatabaseExecutor -- proving the
    whole load-plan -> parse -> execute -> log chain works end-to-end
    against real generator output, without needing a live database."""
    executors: list[MockDatabaseExecutor] = []

    def factory(database: str) -> MockDatabaseExecutor:
        db = MockDatabaseExecutor(rows_affected=3)
        executors.append(db)
        return db

    log_path = tmp_path / "engine_execution_log.json"
    from engine.logger import ExecutionLogger

    engine = Engine(real_output_project, factory, logger=ExecutionLogger(log_path))
    outcomes = engine.run()

    assert len(outcomes) == 6
    assert [o.step.step_id for o in outcomes] == ["1", "2", "3", "4", "5", "6"]
    assert all(o.record.status == ExecutionStatus.SUCCESS for o in outcomes)

    # Each step gets its own executor, and each one goes through the full,
    # correctly-ordered transaction lifecycle -- never execute() before
    # begin_transaction(), never a missing commit or close.
    assert len(executors) == 6
    for db in executors:
        assert db.calls == ["connect", "begin_transaction", "execute", "commit", "close"]

    logged = json.loads(log_path.read_text(encoding="utf-8"))["entries"]
    assert len(logged) == 6
    assert logged[0]["table"] == "DIM_PATIENT"
    assert logged[0]["stage"] == "read"
    assert logged[-1]["table"] == "FACT_PATIENT_VISIT"
    assert logged[-1]["stage"] == "write"
    assert all(e["status"] == "success" for e in logged)
    assert all(e["sql_hash"].startswith("sha256:") for e in logged)


def test_database_mismatch_between_plan_and_sqlx_config_raises(tmp_path: Path) -> None:
    """execution_plan.json's step.database and the .sqlx file's own config
    block both carry the target database, by deliberate design (see
    engine/README.md "Declared vs. observed database"). If a plan or file
    was hand-edited so the two disagree, the engine must refuse to guess
    which one is right rather than silently picking one."""
    project = tmp_path / "project"
    (project / "definitions" / "T").mkdir(parents=True)
    (project / "metadata" / "execution").mkdir(parents=True)

    (project / "definitions" / "T" / "read.sqlx").write_text(
        'config {\n  "stage": "read",\n  "buildspec": "metadata/build/T.buildspec.json",\n'
        '  "database": "intermediate_db"\n}\n\nSELECT 1;',
        encoding="utf-8",
    )
    plan = {
        "generated_at": "2026-01-01T00:00:00Z",
        "steps": [
            {
                "step_id": "1", "table": "T", "stage": "read",
                "database": "wrong_db",
                "file": "definitions/T/read.sqlx", "depends_on": [],
            }
        ],
    }
    (project / "metadata" / "execution" / "execution_plan.json").write_text(
        json.dumps(plan), encoding="utf-8"
    )

    def factory(database: str) -> MockDatabaseExecutor:
        return MockDatabaseExecutor()

    engine = Engine(project, factory)
    with pytest.raises(ValidationError, match="wrong_db.*intermediate_db"):
        engine.run()


def test_stops_immediately_on_failure_and_rolls_back(real_output_project: Path, tmp_path: Path) -> None:
    """The real project's DIM_PATIENT/read.sqlx calls udf_full_name(...), a
    UDF whose SQL body input/user_defined_functions.md never provided (see
    docs/ASSUMPTIONS.md-equivalent note in the final report) -- so on a real
    database this step would genuinely fail. Simulated here by having the
    mock executor raise on that exact SQL, to prove: the failing step rolls
    back and is logged as a failure, ExecutionFailure propagates, and
    execution stops -- no later step (not even DIM_PATIENT's own later
    stages, let alone FACT_PATIENT_VISIT) runs at all."""
    executors: list[MockDatabaseExecutor] = []

    def factory(database: str) -> MockDatabaseExecutor:
        db = MockDatabaseExecutor(fail_on="udf_full_name")
        executors.append(db)
        return db

    log_path = tmp_path / "engine_execution_log.json"
    from engine.logger import ExecutionLogger

    engine = Engine(real_output_project, factory, logger=ExecutionLogger(log_path))

    with pytest.raises(ExecutionFailure, match="DIM_PATIENT.read"):
        engine.run()

    # Exactly one executor was ever created -- the run stopped at the first
    # (and only) step attempted, never reaching step 2.
    assert len(executors) == 1
    failed_db = executors[0]
    assert failed_db.calls == ["connect", "begin_transaction", "execute", "rollback", "close"]
    assert failed_db.committed is False
    assert failed_db.rolled_back is True

    logged = json.loads(log_path.read_text(encoding="utf-8"))["entries"]
    assert len(logged) == 1
    assert logged[0]["status"] == "failure"
    assert logged[0]["table"] == "DIM_PATIENT"
    assert logged[0]["stage"] == "read"
    assert "simulated database failure" in logged[0]["error_message"]
    assert logged[0]["rows_affected"] is None
