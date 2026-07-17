"""
Unit tests for connection-config resolution only. Per this project's current
milestone, live PostgreSQL validation (actually calling PostgresExecutor.connect())
is deferred to a separate, later milestone -- see engine/README.md "Testing".
These tests never open a socket; they only exercise resolve_connection_config's
env-var / .mcp.json fallback logic with fake inputs.
"""

import json
from pathlib import Path

import pytest

from engine.exceptions import DatabaseConnectionError
from engine.postgres import resolve_connection_config


def test_resolves_from_environment_variables(tmp_path: Path) -> None:
    env = {"PGHOST": "db.example", "PGPORT": "5433", "PGUSER": "alice", "PGPASSWORD": "s3cret"}
    config = resolve_connection_config("target_db", mcp_config_path=tmp_path / "missing.json", env=env)
    assert config.host == "db.example"
    assert config.port == 5433
    assert config.user == "alice"
    assert config.password == "s3cret"
    assert config.dbname == "target_db"


def test_defaults_port_when_pgport_unset(tmp_path: Path) -> None:
    env = {"PGHOST": "db.example", "PGUSER": "alice", "PGPASSWORD": "s3cret"}
    config = resolve_connection_config("target_db", mcp_config_path=tmp_path / "missing.json", env=env)
    assert config.port == 5432


def test_raises_when_nothing_resolves(tmp_path: Path) -> None:
    with pytest.raises(DatabaseConnectionError, match="Could not resolve"):
        resolve_connection_config("target_db", mcp_config_path=tmp_path / "missing.json", env={})


def test_empty_mcp_json_falls_through_to_env(tmp_path: Path) -> None:
    mcp_path = tmp_path / ".mcp.json"
    mcp_path.write_text("", encoding="utf-8")
    env = {"PGHOST": "db.example", "PGUSER": "alice", "PGPASSWORD": "s3cret"}
    config = resolve_connection_config("target_db", mcp_config_path=mcp_path, env=env)
    assert config.host == "db.example"


def test_malformed_mcp_json_falls_through_to_env_rather_than_raising(tmp_path: Path) -> None:
    mcp_path = tmp_path / ".mcp.json"
    mcp_path.write_text("{not valid json", encoding="utf-8")
    env = {"PGHOST": "db.example", "PGUSER": "alice", "PGPASSWORD": "s3cret"}
    config = resolve_connection_config("target_db", mcp_config_path=mcp_path, env=env)
    assert config.host == "db.example"


def test_prefers_mcp_json_postgres_server_over_environment(tmp_path: Path) -> None:
    mcp_path = tmp_path / ".mcp.json"
    mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "postgres": {
                        "command": "some-mcp-postgres-server",
                        "env": {
                            "PGHOST": "mcp-host",
                            "PGPORT": "5555",
                            "PGUSER": "mcp-user",
                            "PGPASSWORD": "mcp-pass",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    env = {"PGHOST": "env-host", "PGUSER": "env-user", "PGPASSWORD": "env-pass"}
    config = resolve_connection_config("target_db", mcp_config_path=mcp_path, env=env)
    assert config.host == "mcp-host"
    assert config.port == 5555


def test_ignores_non_postgres_mcp_servers(tmp_path: Path) -> None:
    mcp_path = tmp_path / ".mcp.json"
    mcp_path.write_text(
        json.dumps({"mcpServers": {"github": {"command": "gh-mcp", "env": {"TOKEN": "x"}}}}),
        encoding="utf-8",
    )
    env = {"PGHOST": "db.example", "PGUSER": "alice", "PGPASSWORD": "s3cret"}
    config = resolve_connection_config("target_db", mcp_config_path=mcp_path, env=env)
    assert config.host == "db.example"
