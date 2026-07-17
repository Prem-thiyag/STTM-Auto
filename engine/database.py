"""
Database abstraction. Nothing in this module -- or in any module that
implements it -- may depend on executor.py; the dependency direction is
strictly executor.py -> database.py, never the reverse. This is what lets
executor.py be tested against MockDatabaseExecutor without ever importing
psycopg2, and lets postgres.py be replaced entirely (a different database
engine, a different driver) without executor.py changing at all.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from engine.models import ExecutionResult


class DatabaseExecutor(ABC):
    """A connection to one database, capable of running one SQL statement (or
    semicolon-separated block) inside an explicit transaction. One instance
    is used for exactly one .sqlx file's execution and then closed -- see
    engine/README.md "Transaction model"."""

    @abstractmethod
    def connect(self) -> None:
        """Establish the underlying connection. Idempotent: calling it twice
        without an intervening close() must not raise."""

    @abstractmethod
    def execute(self, sql: str) -> ExecutionResult:
        """Run `sql` against the connected database. Must be called between
        begin_transaction() and commit()/rollback(). Raises on any database
        error -- never swallows one."""

    @abstractmethod
    def begin_transaction(self) -> None:
        """Start an explicit transaction."""

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""

    @abstractmethod
    def rollback(self) -> None:
        """Roll back the current transaction."""

    @abstractmethod
    def close(self) -> None:
        """Release the underlying connection. Idempotent."""


class MockDatabaseExecutor(DatabaseExecutor):
    """In-memory DatabaseExecutor for unit tests only -- never used in
    production. Records every call it receives (`calls`) so a test can assert
    on ordering (connect -> begin_transaction -> execute -> commit/rollback ->
    close) without a real database anywhere in the loop.

    Construct with `fail_on` set to a substring of SQL that should raise, to
    exercise the engine's rollback / stop-on-failure path deterministically.
    """

    def __init__(
        self,
        *,
        rows_affected: int | None = 1,
        fail_on: str | None = None,
        fail_message: str = "simulated database failure",
    ) -> None:
        self.rows_affected = rows_affected
        self.fail_on = fail_on
        self.fail_message = fail_message
        self.calls: list[str] = []
        self.executed_sql: list[str] = []
        self.connected = False
        self.in_transaction = False
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def connect(self) -> None:
        self.calls.append("connect")
        self.connected = True

    def execute(self, sql: str) -> ExecutionResult:
        self.calls.append("execute")
        self.executed_sql.append(sql)
        if self.fail_on is not None and self.fail_on in sql:
            raise RuntimeError(self.fail_message)
        return ExecutionResult(rows_affected=self.rows_affected)

    def begin_transaction(self) -> None:
        self.calls.append("begin_transaction")
        self.in_transaction = True

    def commit(self) -> None:
        self.calls.append("commit")
        self.committed = True
        self.in_transaction = False

    def rollback(self) -> None:
        self.calls.append("rollback")
        self.rolled_back = True
        self.in_transaction = False

    def close(self) -> None:
        self.calls.append("close")
        self.connected = False
        self.closed = True
