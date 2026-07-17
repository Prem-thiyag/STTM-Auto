import json
from pathlib import Path

from engine.logger import ExecutionLogger
from engine.models import ExecutionRecord, ExecutionStatus, Stage


def _record(table: str = "T", status: ExecutionStatus = ExecutionStatus.SUCCESS) -> ExecutionRecord:
    return ExecutionRecord(
        table=table,
        stage=Stage.READ,
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-01T00:00:01Z",
        duration_seconds=1.0,
        status=status,
        rows_affected=5,
        sql_hash="sha256:abc",
        error_message=None,
    )


def test_creates_log_file_on_first_record(tmp_path: Path) -> None:
    log_path = tmp_path / "log.json"
    logger = ExecutionLogger(log_path)
    assert not log_path.exists()
    logger.record(_record())
    assert log_path.exists()
    data = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(data["entries"]) == 1


def test_is_append_only(tmp_path: Path) -> None:
    log_path = tmp_path / "log.json"
    logger = ExecutionLogger(log_path)
    logger.record(_record(table="A"))
    logger.record(_record(table="B"))
    logger.record(_record(table="C"))
    entries = logger.read_all()
    assert [e["table"] for e in entries] == ["A", "B", "C"]


def test_failure_record_shape(tmp_path: Path) -> None:
    log_path = tmp_path / "log.json"
    logger = ExecutionLogger(log_path)
    logger.record(_record(status=ExecutionStatus.FAILURE))
    entries = logger.read_all()
    assert entries[0]["status"] == "failure"
