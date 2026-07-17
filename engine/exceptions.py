"""
Exception hierarchy for the engine.

Every exception the engine raises is a subclass of :class:`EngineError`, and
every one carries a descriptive, specific message -- nothing in this package
raises a bare ``Exception`` or swallows an error silently (see engine/README.md
"Design Principles").
"""

from __future__ import annotations


class EngineError(Exception):
    """Base class for every exception this package raises."""


class SQLXParseError(EngineError):
    """A .sqlx file's config block is missing, malformed, or fails validation."""


class ExecutionPlanError(EngineError):
    """execution_plan.json is missing, malformed, or internally inconsistent
    (e.g. a step's depends_on references a step_id that doesn't exist, or that
    appears later in the plan than the step depending on it)."""


class DatabaseConnectionError(EngineError):
    """A DatabaseExecutor could not establish or resolve a connection."""


class ExecutionFailure(EngineError):
    """A stage's SQL execution failed. Raised by Engine.run() after the
    failing stage has been rolled back and logged, to stop the run."""


class ValidationError(EngineError):
    """A loaded artifact (execution plan, buildspec reference, config block)
    is structurally present but fails a required-field or type check."""
