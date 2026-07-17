"""
SQLX file parser.

A .sqlx file has exactly two sections: a `config { ... }` block (a JSON
object, once the `config` keyword and its wrapping braces are stripped off),
then a blank line, then arbitrary SQL. This module parses ONLY the config
block. Everything after it is treated as an opaque string -- never
tokenized, validated, rewritten, or otherwise interpreted as SQL. See
engine/README.md "SQLX format" for the full contract and why it's designed
this way (the engine performs zero reasoning about what the SQL does).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from engine.exceptions import SQLXParseError
from engine.models import SqlxConfig, SqlxFile, Stage
from engine.utils import find_matching_brace

_CONFIG_KEYWORD_RE = re.compile(r"config\s*\{", re.MULTILINE)
_REQUIRED_CONFIG_KEYS = ("stage", "buildspec", "database")
_VALID_STAGES = {s.value for s in Stage}


def parse_sqlx(path: Path) -> SqlxFile:
    """Load and parse a .sqlx file. Raises SQLXParseError with a message that
    names the file and the specific problem for every failure mode: file not
    found, no config block, malformed JSON, missing required property,
    invalid stage value."""
    if not path.exists():
        raise SQLXParseError(f"{path}: file not found")

    text = path.read_text(encoding="utf-8")

    match = _CONFIG_KEYWORD_RE.search(text)
    if match is None:
        raise SQLXParseError(
            f"{path}: no `config {{ ... }}` block found. Every .sqlx file must open "
            f"with one -- see references/sqlx-syntax-guide.md in the sqlx-etl-generator skill."
        )

    open_brace_index = match.end() - 1  # match ends just past '{'
    try:
        close_brace_index = find_matching_brace(text, open_brace_index)
    except ValueError as exc:
        raise SQLXParseError(f"{path}: config block has unbalanced braces ({exc})") from exc

    config_text = text[open_brace_index : close_brace_index + 1]
    try:
        config_data = json.loads(config_text)
    except json.JSONDecodeError as exc:
        raise SQLXParseError(
            f"{path}: config block is not valid JSON ({exc}). Config block content: {config_text!r}"
        ) from exc

    if not isinstance(config_data, dict):
        raise SQLXParseError(f"{path}: config block must be a JSON object, got {type(config_data).__name__}")

    missing = [key for key in _REQUIRED_CONFIG_KEYS if key not in config_data]
    if missing:
        raise SQLXParseError(
            f"{path}: config block is missing required propert{'y' if len(missing) == 1 else 'ies'}: "
            f"{', '.join(missing)}"
        )

    stage_value = config_data["stage"]
    if stage_value not in _VALID_STAGES:
        raise SQLXParseError(
            f"{path}: config.stage is {stage_value!r}, expected one of {sorted(_VALID_STAGES)}"
        )

    buildspec_value = config_data["buildspec"]
    if not isinstance(buildspec_value, str) or not buildspec_value:
        raise SQLXParseError(f"{path}: config.buildspec must be a non-empty string")

    database_value = config_data["database"]
    if not isinstance(database_value, str) or not database_value:
        raise SQLXParseError(f"{path}: config.database must be a non-empty string")

    # `version` is optional -- present on every file the current generator
    # writes, but not required, so a hand-written or older .sqlx file without
    # one still parses (see docs/ASSUMPTIONS.md "Generated .sqlx files carry
    # a config block").
    version_value = config_data.get("version")
    if version_value is not None and not isinstance(version_value, str):
        raise SQLXParseError(f"{path}: config.version must be a string when present")

    sql = text[close_brace_index + 1 :].strip()
    if not sql:
        raise SQLXParseError(f"{path}: no SQL found after the config block")

    config = SqlxConfig(
        stage=Stage(stage_value),
        buildspec=buildspec_value,
        database=database_value,
        version=version_value,
    )
    return SqlxFile(path=path, config=config, sql=sql)
