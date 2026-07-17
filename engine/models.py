"""
Typed data model for the engine.

Plain dataclasses throughout, not Pydantic: every one of these is small,
internal, and constructed from already-validated data (parser.py and
planner.py raise their own descriptive exceptions before a model is ever
built), so a validation framework would add a dependency without adding
value here. Every field is typed; nothing is `Any`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path


class Stage(str, Enum):
    """The three stages a target table's SQLX is split into. Values match the
    `stage` field of a .sqlx file's config block exactly."""

    READ = "read"
    PROCESS = "process"
    WRITE = "write"


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class SqlxConfig:
    """The parsed `config { ... }` block of a .sqlx file. `version` is
    optional (older or hand-written .sqlx files may omit it); when present
    it identifies the config block's own shape, not the pipeline's."""

    stage: Stage
    buildspec: str
    database: str
    version: str | None = None


@dataclass(frozen=True)
class SqlxFile:
    """A fully parsed .sqlx file: its config block and the SQL that follows it."""

    path: Path
    config: SqlxConfig
    sql: str


@dataclass(frozen=True)
class ExecutionStep:
    """One entry in execution_plan.json's `steps` array. No `command` field:
    execution_plan.json is declarative (step_id/table/stage/database/file/
    depends_on only) so it stays usable by both the human-facing Execute plan
    and this engine without favoring either's execution mechanism -- see
    engine/README.md "Execution plan is declarative"."""

    step_id: str
    table: str
    stage: Stage
    database: str
    file: str
    depends_on: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExecutionPlan:
    """The full, ordered execution_plan.json -- the planner's sole source of
    truth. `steps` is always in the exact order the file declared; the
    planner validates that order, it never computes or changes it."""

    generated_at: str
    steps: tuple[ExecutionStep, ...]


@dataclass(frozen=True)
class ExecutionResult:
    """What a DatabaseExecutor.execute() call reports back."""

    rows_affected: int | None


@dataclass(frozen=True)
class ExecutionRecord:
    """One append-only entry in the engine's execution log. Field set matches
    engine/README.md's "Logging model" section exactly: table, stage,
    start_time, end_time, duration, status, rows_affected, SQL hash,
    error_message."""

    table: str
    stage: Stage
    start_time: str
    end_time: str
    duration_seconds: float
    status: ExecutionStatus
    rows_affected: int | None
    sql_hash: str
    error_message: str | None


@dataclass(frozen=True)
class ConnectionConfig:
    """Injectable PostgreSQL connection parameters. Never constructed with a
    hardcoded credential anywhere in this package -- always supplied by the
    caller or resolved from the environment / .mcp.json at the call site."""

    host: str
    port: int
    dbname: str
    user: str
    password: str

    def with_database(self, dbname: str) -> "ConnectionConfig":
        """A stage's config block names the database to run against; the rest
        of the connection (host/port/user/password) is shared. This returns a
        copy pointed at a different database rather than mutating in place --
        every model in this module is frozen."""
        return replace(self, dbname=dbname)
