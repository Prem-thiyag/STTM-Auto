"""
PostgreSQL implementation of DatabaseExecutor, plus connection-config
resolution.

Design note: PostgresExecutor itself never resolves its own credentials --
it is constructed with a ConnectionConfig the caller supplies. Resolution
(env vars, .mcp.json, explicit override) is a separate, standalone function,
`resolve_connection_config()`, so it can be swapped, tested, or bypassed
independently of the executor that uses its result. This is what "the Runtime
should not hardcode credentials; connection configuration should be
injectable" means in practice: there is no code path in this file that reads
a password literal.

psycopg2 (not psycopg3) is used because it's already present in this
environment and is a stable, widely deployed driver; nothing here depends on
a psycopg2-specific feature psycopg3 lacks, so swapping drivers later is a
one-file change.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from engine.exceptions import DatabaseConnectionError
from engine.database import DatabaseExecutor
from engine.models import ConnectionConfig, ExecutionResult

try:
    import psycopg2
except ImportError:  # pragma: no cover - exercised only when the driver truly isn't installed
    psycopg2 = None  # type: ignore[assignment]

DEFAULT_PORT = 5432


def resolve_connection_config(
    dbname: str,
    *,
    mcp_config_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> ConnectionConfig:
    """Resolve connection parameters for `dbname`, preferring, in order:

    1. An MCP server definition in `.mcp.json` (repository root) whose name
       or command suggests PostgreSQL -- "MCP configuration (preferred)".
    2. Standard PostgreSQL environment variables (PGHOST, PGPORT, PGUSER,
       PGPASSWORD) -- "standard PostgreSQL connection... for local
       development and testing".

    Raises DatabaseConnectionError, never returns a partially-filled or
    guessed config, if neither source has enough information.
    """
    env = os.environ if env is None else env

    mcp_config = _try_mcp_config(mcp_config_path or Path(".mcp.json"), dbname, env)
    if mcp_config is not None:
        return mcp_config

    host = env.get("PGHOST")
    user = env.get("PGUSER")
    password = env.get("PGPASSWORD")
    port = int(env.get("PGPORT", DEFAULT_PORT))

    if host and user and password is not None:
        return ConnectionConfig(host=host, port=port, dbname=dbname, user=user, password=password)

    raise DatabaseConnectionError(
        f"Could not resolve PostgreSQL connection parameters for database "
        f"'{dbname}': no usable server found in .mcp.json, and PGHOST/PGUSER/"
        f"PGPASSWORD are not all set in the environment. Supply a "
        f"ConnectionConfig explicitly instead of relying on resolution, or "
        f"set the standard PG* environment variables."
    )


def _try_mcp_config(
    mcp_config_path: Path, dbname: str, env: dict[str, str]
) -> ConnectionConfig | None:
    """Best-effort extraction of Postgres connection details from a Claude
    Code `.mcp.json`. Returns None (never raises) if the file is absent,
    empty, unparsable, or doesn't contain anything postgres-shaped -- MCP
    config is a preference, not a requirement, and a malformed .mcp.json
    should fall through to the environment-variable path, not hard-fail."""
    if not mcp_config_path.exists():
        return None
    try:
        raw = mcp_config_path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None

    servers = data.get("mcpServers", {})
    for name, server in servers.items():
        if "postgres" not in name.lower():
            continue
        server_env = server.get("env", {})
        host = server_env.get("PGHOST") or server_env.get("POSTGRES_HOST")
        user = server_env.get("PGUSER") or server_env.get("POSTGRES_USER")
        password = server_env.get("PGPASSWORD") or server_env.get("POSTGRES_PASSWORD")
        port = server_env.get("PGPORT") or server_env.get("POSTGRES_PORT") or DEFAULT_PORT
        if host and user and password is not None:
            return ConnectionConfig(
                host=host, port=int(port), dbname=dbname, user=user, password=password
            )
    return None


class PostgresExecutor(DatabaseExecutor):
    """DatabaseExecutor backed by a real PostgreSQL connection via psycopg2.

    Not verified against a live database as of this writing -- see
    engine/README.md "Testing" and docs/ASSUMPTIONS-equivalent notes there.
    Structurally exercised via MockDatabaseExecutor in engine/tests/.
    """

    def __init__(self, config: ConnectionConfig) -> None:
        if psycopg2 is None:
            raise DatabaseConnectionError(
                "psycopg2 is not installed. Install with: pip install -r engine/requirements.txt"
            )
        self._config = config
        self._conn = None

    def connect(self) -> None:
        if self._conn is not None:
            return
        try:
            self._conn = psycopg2.connect(
                host=self._config.host,
                port=self._config.port,
                dbname=self._config.dbname,
                user=self._config.user,
                password=self._config.password,
            )
            self._conn.autocommit = False
        except psycopg2.OperationalError as exc:
            raise DatabaseConnectionError(
                f"Could not connect to PostgreSQL database '{self._config.dbname}' "
                f"at {self._config.host}:{self._config.port}: {exc}"
            ) from exc

    def execute(self, sql: str) -> ExecutionResult:
        if self._conn is None:
            raise DatabaseConnectionError("execute() called before connect()")
        with self._conn.cursor() as cursor:
            cursor.execute(sql)
            rows_affected = cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else None
        return ExecutionResult(rows_affected=rows_affected)

    def begin_transaction(self) -> None:
        # psycopg2 opens a transaction implicitly on the first execute() when
        # autocommit is False (set in connect()); nothing to do explicitly,
        # but the method exists so callers never need to know that detail.
        if self._conn is None:
            raise DatabaseConnectionError("begin_transaction() called before connect()")

    def commit(self) -> None:
        if self._conn is None:
            raise DatabaseConnectionError("commit() called before connect()")
        self._conn.commit()

    def rollback(self) -> None:
        if self._conn is None:
            raise DatabaseConnectionError("rollback() called before connect()")
        self._conn.rollback()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
