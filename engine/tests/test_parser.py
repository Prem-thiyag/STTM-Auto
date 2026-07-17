from pathlib import Path

import pytest

from engine.exceptions import SQLXParseError
from engine.models import Stage
from engine.parser import parse_sqlx


def test_parses_real_generated_read_sqlx(real_output_project: Path) -> None:
    sqlx_file = parse_sqlx(real_output_project / "definitions" / "DIM_PATIENT" / "read.sqlx")
    assert sqlx_file.config.stage == Stage.READ
    assert sqlx_file.config.buildspec == "metadata/build/DIM_PATIENT.buildspec.json"
    assert sqlx_file.config.database == "intermediate_db"
    assert sqlx_file.config.version == "1.0"
    assert "CREATE TABLE IF NOT EXISTS stg_dim_patient" in sqlx_file.sql
    assert "ROW_NUMBER() OVER (ORDER BY" in sqlx_file.sql  # GENERATED patient_key column
    assert "config {" not in sqlx_file.sql  # config block must not leak into the SQL


def test_parses_real_generated_write_sqlx_with_target_database(real_output_project: Path) -> None:
    sqlx_file = parse_sqlx(real_output_project / "definitions" / "FACT_PATIENT_VISIT" / "write.sqlx")
    assert sqlx_file.config.stage == Stage.WRITE
    assert sqlx_file.config.database == "target_db"


def test_all_six_real_sqlx_files_parse(real_output_project: Path) -> None:
    for table in ("DIM_PATIENT", "FACT_PATIENT_VISIT"):
        for stage in ("read", "process", "write"):
            sqlx_file = parse_sqlx(real_output_project / "definitions" / table / f"{stage}.sqlx")
            assert sqlx_file.config.stage.value == stage


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(SQLXParseError, match="file not found"):
        parse_sqlx(tmp_path / "does_not_exist.sqlx")


def test_missing_config_block_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad.sqlx"
    f.write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(SQLXParseError, match="no `config"):
        parse_sqlx(f)


def test_malformed_json_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad.sqlx"
    f.write_text('config {\n  "stage": "read",\n}\n\nSELECT 1;', encoding="utf-8")
    with pytest.raises(SQLXParseError, match="not valid JSON"):
        parse_sqlx(f)


def test_missing_required_property_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad.sqlx"
    f.write_text('config {\n  "stage": "read"\n}\n\nSELECT 1;', encoding="utf-8")
    with pytest.raises(SQLXParseError, match="missing required propert"):
        parse_sqlx(f)


def test_invalid_stage_value_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad.sqlx"
    f.write_text(
        'config {\n  "stage": "transform",\n  "buildspec": "x.json",\n  "database": "d"\n}\n\nSELECT 1;',
        encoding="utf-8",
    )
    with pytest.raises(SQLXParseError, match="expected one of"):
        parse_sqlx(f)


def test_no_sql_after_config_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad.sqlx"
    f.write_text(
        'config {\n  "stage": "read",\n  "buildspec": "x.json",\n  "database": "d"\n}\n',
        encoding="utf-8",
    )
    with pytest.raises(SQLXParseError, match="no SQL found"):
        parse_sqlx(f)


def test_version_field_is_optional_but_parsed_when_present(tmp_path: Path) -> None:
    f = tmp_path / "with_version.sqlx"
    f.write_text(
        'config {\n  "stage": "read",\n  "buildspec": "x.json",\n  "database": "d",\n'
        '  "version": "1.0"\n}\n\nSELECT 1;',
        encoding="utf-8",
    )
    sqlx_file = parse_sqlx(f)
    assert sqlx_file.config.version == "1.0"


def test_version_field_absent_defaults_to_none(tmp_path: Path) -> None:
    f = tmp_path / "no_version.sqlx"
    f.write_text(
        'config {\n  "stage": "read",\n  "buildspec": "x.json",\n  "database": "d"\n}\n\nSELECT 1;',
        encoding="utf-8",
    )
    sqlx_file = parse_sqlx(f)
    assert sqlx_file.config.version is None


def test_non_string_version_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad_version.sqlx"
    f.write_text(
        'config {\n  "stage": "read",\n  "buildspec": "x.json",\n  "database": "d",\n'
        '  "version": 1\n}\n\nSELECT 1;',
        encoding="utf-8",
    )
    with pytest.raises(SQLXParseError, match="version must be a string"):
        parse_sqlx(f)


def test_nested_braces_in_config_do_not_confuse_the_parser(tmp_path: Path) -> None:
    # A defensive test: config values could in principle contain braces (e.g.
    # inside a string). find_matching_brace must track string state, not just
    # brace depth, or a value like this would truncate the block early.
    f = tmp_path / "nested.sqlx"
    f.write_text(
        'config {\n  "stage": "read",\n  "buildspec": "x.json",\n  "database": "d",\n'
        '  "note": "contains a brace } inside a string"\n}\n\nSELECT 1;',
        encoding="utf-8",
    )
    sqlx_file = parse_sqlx(f)
    assert sqlx_file.sql == "SELECT 1;"
