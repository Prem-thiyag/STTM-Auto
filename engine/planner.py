"""
Execution planner.

Reads `metadata/execution/execution_plan.json` and nothing else. The plan's
own `steps` order IS the execution order -- this module validates that the
order is internally consistent (every dependency is a real step, and appears
before the step that depends on it) and then hands that exact sequence back
unchanged. It never computes an order, never reorders steps to "fix" a bad
dependency, and never infers a dependency the file doesn't state. An
inconsistent plan is a hard error (ExecutionPlanError), not something to
route around -- see engine/README.md "Execution planner".
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.exceptions import ExecutionPlanError
from engine.models import ExecutionPlan, ExecutionStep, Stage

_REQUIRED_STEP_KEYS = ("step_id", "table", "stage", "database", "file", "depends_on")
_VALID_STAGES = {s.value for s in Stage}

DEFAULT_PLAN_RELATIVE_PATH = Path("metadata") / "execution" / "execution_plan.json"


class ExecutionPlanner:
    """Loads and validates one project's execution plan.

    `project_root` is the generated project's root (i.e. the skill's
    `output/` directory, or wherever it was pointed) -- the same directory
    `parser.py` resolves every `file` path against.
    """

    def __init__(self, project_root: Path, plan_path: Path | None = None) -> None:
        self.project_root = project_root
        self.plan_path = plan_path or (project_root / DEFAULT_PLAN_RELATIVE_PATH)

    def load_plan(self) -> ExecutionPlan:
        if not self.plan_path.exists():
            raise ExecutionPlanError(f"{self.plan_path}: execution plan not found")

        try:
            data = json.loads(self.plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ExecutionPlanError(f"{self.plan_path}: not valid JSON ({exc})") from exc

        if "generated_at" not in data or "steps" not in data:
            raise ExecutionPlanError(
                f"{self.plan_path}: missing required top-level key(s) "
                f"(need 'generated_at' and 'steps')"
            )

        raw_steps = data["steps"]
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ExecutionPlanError(f"{self.plan_path}: 'steps' must be a non-empty array")

        steps = [self._parse_step(i, raw) for i, raw in enumerate(raw_steps)]
        self._validate_dependency_order(steps)

        return ExecutionPlan(generated_at=data["generated_at"], steps=tuple(steps))

    def sequence(self) -> tuple[ExecutionStep, ...]:
        """The validated steps, in the exact order execution_plan.json gave
        them. Calling this is equivalent to `load_plan().steps` -- provided
        as the single obvious entry point for `executor.py`."""
        return self.load_plan().steps

    def _parse_step(self, index: int, raw: dict) -> ExecutionStep:
        if not isinstance(raw, dict):
            raise ExecutionPlanError(f"{self.plan_path}: steps[{index}] is not an object")

        missing = [k for k in _REQUIRED_STEP_KEYS if k not in raw]
        if missing:
            raise ExecutionPlanError(
                f"{self.plan_path}: steps[{index}] is missing required key(s): {', '.join(missing)}"
            )

        if raw["stage"] not in _VALID_STAGES:
            raise ExecutionPlanError(
                f"{self.plan_path}: steps[{index}].stage is {raw['stage']!r}, "
                f"expected one of {sorted(_VALID_STAGES)}"
            )

        depends_on = raw["depends_on"]
        if not isinstance(depends_on, list):
            raise ExecutionPlanError(f"{self.plan_path}: steps[{index}].depends_on must be an array")

        if not isinstance(raw["database"], str) or not raw["database"]:
            raise ExecutionPlanError(
                f"{self.plan_path}: steps[{index}].database must be a non-empty string"
            )

        return ExecutionStep(
            step_id=raw["step_id"],
            table=raw["table"],
            stage=Stage(raw["stage"]),
            database=raw["database"],
            file=raw["file"],
            depends_on=tuple(depends_on),
        )

    def _validate_dependency_order(self, steps: list[ExecutionStep]) -> None:
        """Every depends_on id must (a) exist as some step's step_id and (b)
        appear earlier in the list than the step that depends on it. This is
        a validation of the order already given, not a computation of a new
        one -- if it fails, the plan itself is wrong and must be regenerated
        by Generate, not silently reordered here."""
        seen: set[str] = set()
        step_ids = {s.step_id for s in steps}

        seen_ids: set[str] = set()
        for step in steps:
            if step.step_id in seen_ids:
                raise ExecutionPlanError(
                    f"{self.plan_path}: duplicate step_id '{step.step_id}'"
                )
            seen_ids.add(step.step_id)

        for step in steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise ExecutionPlanError(
                        f"{self.plan_path}: step '{step.step_id}' depends_on unknown "
                        f"step_id '{dep}'"
                    )
                if dep not in seen:
                    raise ExecutionPlanError(
                        f"{self.plan_path}: step '{step.step_id}' depends_on '{dep}', which "
                        f"appears later in the plan (or not at all before it) -- the plan's "
                        f"own step order must already be a valid topological order; the "
                        f"planner does not reorder it."
                    )
            seen.add(step.step_id)
