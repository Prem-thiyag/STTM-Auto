"""
Database lifecycle orchestration for a generated SQLX ETL project: resetting
the three PostgreSQL databases a project expects (source/intermediate/target)
and running its bootstrap/ SQL in the order bootstrap/README.md documents for
a human to run manually. This module is the automated equivalent of that
manual sequence -- it contains only orchestration (which statement runs
against which database, in what order, with what psql variables); connection
resolution is entirely engine.postgres.resolve_connection_config, and no
statement here duplicates anything executor.py/parser.py/planner.py already
do (those run a generated project's definitions/*.sqlx; this runs its
bootstrap/*.sql, a different artifact set with a different owner -- see
ARCHITECTURE.md's ownership table).

CREATE DATABASE / DROP DATABASE cannot run inside a transaction block, so
reset_databases() uses a dedicated autocommit connection to the 'postgres'
maintenance database via psycopg2 (already a dependency of engine.postgres).
Bootstrap SQL files are run via the psql CLI, not psycopg2, because the two
cross-database FDW bridge scripts use psql's own `-v name=value` variable
substitution (`:'remote_host'` etc. -- see bootstrap/README.md and
templates/bootstrap/fdw*.sql.tmpl in the skill) to inject the *other*
database's connection details; psycopg2 has no equivalent mechanism, and
reimplementing psql's variable substitution would duplicate functionality
that already exists and is already the documented, human-run mechanism.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from engine.exceptions import DatabaseConnectionError, EngineError
from engine.models import ConnectionConfig
from engine.postgres import resolve_connection_config

try:
    import psycopg2
except ImportError:  # pragma: no cover - exercised only when the driver truly isn't installed
    psycopg2 = None  # type: ignore[assignment]

MANAGED_DATABASES: tuple[str, ...] = ("source_db", "intermediate_db", "target_db")

# (bootstrap-relative path, database(s) to run it against, "remote" database whose
# connection details must be supplied as psql -v variables, or None). Order matters:
# each step's preconditions are satisfied by every step before it -- see
# bootstrap/README.md "Run order" for the human-facing version of this same sequence.
_BOOTSTRAP_STEPS: tuple[tuple[str, tuple[str, ...] | str, str | None], ...] = (
    ("db/01_init/01_create_schemas.sql", MANAGED_DATABASES, None),
    ("db/02_source/ddl_source_tables.sql", "source_db", None),
    ("db/04_target/ddl_target_tables.sql", "target_db", None),
    ("db/01_init/02_create_fdw_intermediate_to_source.sql", "intermediate_db", "source_db"),
    ("db/01_init/04_create_fdw_intermediate_to_target.sql", "intermediate_db", "target_db"),
    ("db/03_intermediate/init_staging_schema.sql", "intermediate_db", None),
    ("db/03_intermediate/create_udfs.sql", "intermediate_db", None),
    ("db/01_init/03_create_fdw_target_to_intermediate.sql", "target_db", "intermediate_db"),
)


class BootstrapError(EngineError):
    """A bootstrap SQL file failed to execute."""


class BootstrapStepResult:
    __slots__ = ("file", "database", "returncode", "stdout", "stderr")

    def __init__(self, file: str, database: str, returncode: int, stdout: str, stderr: str) -> None:
        self.file = file
        self.database = database
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def admin_connection(config: ConnectionConfig):
    if psycopg2 is None:
        raise DatabaseConnectionError(
            "psycopg2 is not installed. Install with: pip install -r engine/requirements.txt"
        )
    conn = psycopg2.connect(
        host=config.host, port=config.port, dbname="postgres", user=config.user, password=config.password
    )
    conn.autocommit = True  # CREATE/DROP DATABASE cannot run inside a transaction block
    return conn


def reset_databases(
    config: ConnectionConfig, databases: tuple[str, ...] = MANAGED_DATABASES
) -> list[str]:
    """Terminate any other sessions on each database, then DROP + CREATE it
    fresh. `databases` defaults to exactly the three this project's generated
    pipeline expects (MANAGED_DATABASES) -- never an arbitrary caller-supplied
    name, since these are interpolated directly into DDL."""
    unknown = set(databases) - set(MANAGED_DATABASES)
    if unknown:
        raise ValueError(f"refusing to reset non-pipeline database(s): {sorted(unknown)}")

    conn = admin_connection(config)
    reset: list[str] = []
    try:
        with conn.cursor() as cur:
            for db in databases:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid();",
                    (db,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{db}";')
                cur.execute(f'CREATE DATABASE "{db}";')
                reset.append(db)
    finally:
        conn.close()
    return reset


def _run_psql(
    file_path: Path, dbname: str, config: ConnectionConfig, remote: ConnectionConfig | None
) -> subprocess.CompletedProcess:
    cmd = [
        "psql", "-h", config.host, "-p", str(config.port), "-U", config.user,
        "-d", dbname, "-v", "ON_ERROR_STOP=1",
    ]
    if remote is not None:
        cmd += [
            "-v", f"remote_host={remote.host}",
            "-v", f"remote_port={remote.port}",
            "-v", f"remote_user={remote.user}",
            "-v", f"remote_password={remote.password}",
        ]
    cmd += ["-f", str(file_path)]
    env = {**os.environ, "PGPASSWORD": config.password}
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def run_bootstrap(project_root: Path, config: ConnectionConfig) -> list[BootstrapStepResult]:
    """Run every bootstrap/*.sql step against the right database, in the
    documented order, stopping immediately on the first failure (matching the
    engine's own executor.py stop-on-failure rule). `config`'s host/port/user/
    password are used for every database this project manages -- they're all
    on the same PostgreSQL instance -- so it also supplies the "remote" psql
    variables for the two FDW bridge scripts."""
    bootstrap_dir = project_root / "bootstrap"
    if not bootstrap_dir.exists():
        raise BootstrapError(f"{bootstrap_dir} not found -- run Generate first.")

    results: list[BootstrapStepResult] = []
    for rel_path, target, remote_db in _BOOTSTRAP_STEPS:
        file_path = bootstrap_dir / rel_path
        if not file_path.exists():
            raise BootstrapError(f"{file_path} not found -- Generate did not produce it.")
        targets = target if isinstance(target, tuple) else (target,)
        remote = config.with_database(remote_db) if remote_db is not None else None
        for dbname in targets:
            proc = _run_psql(file_path, dbname, config, remote)
            results.append(BootstrapStepResult(rel_path, dbname, proc.returncode, proc.stdout, proc.stderr))
            if proc.returncode != 0:
                raise BootstrapError(
                    f"bootstrap step failed: {rel_path} against {dbname} "
                    f"(exit {proc.returncode}): {proc.stderr.strip()}"
                )
    return results


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()  # repo-root .env -> os.environ, if present; never overwrites already-set vars
    except ImportError:  # pragma: no cover - exercised only when python-dotenv truly isn't installed
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seed", "bootstrap"])
    parser.add_argument("project_root", nargs="?", default="output", type=Path)
    args = parser.parse_args()

    try:
        config = resolve_connection_config("postgres")
    except EngineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        if args.action == "seed":
            reset = reset_databases(config)
            print(f"Reset {len(reset)} database(s): {', '.join(reset)}")
        else:
            results = run_bootstrap(args.project_root, config)
            for r in results:
                print(f"OK  {r.file:<55} -> {r.database}")
            print(f"\n{len(results)} bootstrap step(s) completed successfully.")
    except EngineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
