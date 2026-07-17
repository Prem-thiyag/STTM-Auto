import json
from pathlib import Path

import pytest

from engine.exceptions import ExecutionPlanError
from engine.planner import ExecutionPlanner


def test_loads_real_execution_plan_in_declared_order(real_output_project: Path) -> None:
    planner = ExecutionPlanner(real_output_project)
    plan = planner.load_plan()
    assert [s.step_id for s in plan.steps] == ["1", "2", "3", "4", "5", "6"]
    assert [s.table for s in plan.steps] == [
        "DIM_PATIENT", "DIM_PATIENT", "DIM_PATIENT",
        "FACT_PATIENT_VISIT", "FACT_PATIENT_VISIT", "FACT_PATIENT_VISIT",
    ]
    # step 5 (FACT_PATIENT_VISIT.process) depends on step 3 (DIM_PATIENT.write)
    # per the LOOKUP dependency -- confirm the planner preserved it, not derived it.
    step5 = plan.steps[4]
    assert step5.stage.value == "process"
    assert "3" in step5.depends_on


def test_missing_plan_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ExecutionPlanError, match="not found"):
        ExecutionPlanner(tmp_path).load_plan()


def test_malformed_json_raises(tmp_path: Path) -> None:
    plan_dir = tmp_path / "metadata" / "execution"
    plan_dir.mkdir(parents=True)
    (plan_dir / "execution_plan.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ExecutionPlanError, match="not valid JSON"):
        ExecutionPlanner(tmp_path).load_plan()


def _write_plan(tmp_path: Path, steps: list[dict]) -> Path:
    plan_dir = tmp_path / "metadata" / "execution"
    plan_dir.mkdir(parents=True)
    plan_path = plan_dir / "execution_plan.json"
    plan_path.write_text(json.dumps({"generated_at": "2026-01-01T00:00:00Z", "steps": steps}), encoding="utf-8")
    return plan_path


def test_missing_database_key_raises(tmp_path: Path) -> None:
    _write_plan(tmp_path, [
        {"step_id": "1", "table": "T", "stage": "read", "file": "f1", "depends_on": []},
    ])
    with pytest.raises(ExecutionPlanError, match="missing required key"):
        ExecutionPlanner(tmp_path).load_plan()


def test_empty_database_value_raises(tmp_path: Path) -> None:
    _write_plan(tmp_path, [
        {"step_id": "1", "table": "T", "stage": "read", "database": "", "file": "f1", "depends_on": []},
    ])
    with pytest.raises(ExecutionPlanError, match="database must be a non-empty string"):
        ExecutionPlanner(tmp_path).load_plan()


def test_dependency_on_unknown_step_raises(tmp_path: Path) -> None:
    _write_plan(tmp_path, [
        {"step_id": "1", "table": "T", "stage": "read", "database": "d", "file": "f", "depends_on": ["99"]},
    ])
    with pytest.raises(ExecutionPlanError, match="unknown step_id"):
        ExecutionPlanner(tmp_path).load_plan()


def test_dependency_appearing_later_raises(tmp_path: Path) -> None:
    # step 1 depends on step 2, but step 2 comes after it in the list --
    # the planner must reject this, never silently reorder to fix it.
    _write_plan(tmp_path, [
        {"step_id": "1", "table": "T", "stage": "read", "database": "d", "file": "f1", "depends_on": ["2"]},
        {"step_id": "2", "table": "T", "stage": "process", "database": "d", "file": "f2", "depends_on": []},
    ])
    with pytest.raises(ExecutionPlanError, match="appears later"):
        ExecutionPlanner(tmp_path).load_plan()


def test_duplicate_step_id_raises(tmp_path: Path) -> None:
    _write_plan(tmp_path, [
        {"step_id": "1", "table": "T", "stage": "read", "database": "d", "file": "f1", "depends_on": []},
        {"step_id": "1", "table": "T", "stage": "process", "database": "d", "file": "f2", "depends_on": []},
    ])
    with pytest.raises(ExecutionPlanError, match="duplicate step_id"):
        ExecutionPlanner(tmp_path).load_plan()


def test_valid_forward_only_order_passes(tmp_path: Path) -> None:
    plan_path = _write_plan(tmp_path, [
        {"step_id": "1", "table": "T", "stage": "read", "database": "d", "file": "f1", "depends_on": []},
        {"step_id": "2", "table": "T", "stage": "process", "database": "d", "file": "f2", "depends_on": ["1"]},
    ])
    plan = ExecutionPlanner(tmp_path, plan_path).load_plan()
    assert len(plan.steps) == 2
