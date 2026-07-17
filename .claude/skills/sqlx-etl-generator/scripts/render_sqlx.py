#!/usr/bin/env python3
"""
Deterministic buildspec -> SQLX renderer.

Owned by the SQLX Generator specialist (see specialists/sqlx-generator.md). This script
reads ONLY metadata/build/<TABLE>.buildspec.json files -- never source_schema.json,
target_schema.json, sttm.json, or udf.md. Every value it needs to render read.sqlx,
process.sqlx, and write.sqlx must already be present in the buildspec; if it isn't, this
script fails rather than inferring or re-deriving it. That is the load-bearing rule in
ADR-001 that keeps rendering cost flat regardless of source-document complexity.

Naming conventions this script assumes (documented in references/naming-conventions.md,
and which the Mapping Resolver specialist must follow when writing joins[].on and
columns[].expression):
  - Foreign schema alias for reading database X via postgres_fdw is: fdw_<X>
  - A table's staging shape (metadata/build/*.staging_table) lives in the intermediate
    database (--intermediate-database, default "intermediate_db") and is read from
    target_database via the fdw_<intermediate_database> foreign schema in write.sqlx.

Usage:
    python render_sqlx.py <buildspec.json | build_dir> \
        --templates-dir <dir containing read/process/write.sqlx.tmpl> \
        --output-dir <definitions/> \
        [--intermediate-database intermediate_db] \
        [--schema <buildspec.schema.json>]

Prints a JSON array of {"path": ..., "hash": "sha256:..."} for every file written, to
stdout, on success -- this is what the Artifact Generator specialist consumes to build
metadata/manifest.json's generated_files list.

Exit codes:
    0  success
    2  a buildspec failed schema validation
    3  a buildspec requested a load_strategy with no renderer yet
    4  a buildspec is internally inconsistent (e.g. a join references an unlisted table)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema is required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(1)

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
except ImportError:
    print("ERROR: jinja2 is required. Install with: pip install jinja2", file=sys.stderr)
    sys.exit(1)

# Renderers that exist today. A buildspec whose load_strategy isn't in this set is a
# valid IR value (the schema reserves it) with no template yet -- per ADR-001 §9, that
# MUST fail loudly, never silently fall back to full_load.
SUPPORTED_LOAD_STRATEGIES = {"full_load"}

# The SQLX config block's own `version` field (see references/sqlx-syntax-guide.md
# "config block") -- identifies the shape of the config block itself, not the
# pipeline or buildspec. Bump only if the config block's own JSON shape changes
# in a way engine/parser.py needs to distinguish.
SQLX_VERSION = "1.0"


def fdw_alias(database: str) -> str:
    return f"fdw_{database}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def load_buildspec(path: Path, schema: dict) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=schema)
    return data


def render_generator_expression(generator: dict, qualify, base_table: str) -> str:
    """Turn a buildspec column's semantic `generator` object into a concrete SQL
    expression. This is the one place a GENERATED column's SQL shape is decided --
    the Mapping Resolver writes *what kind* of generator (ROW_NUMBER / SEQUENCE /
    UUID / DEFAULT) and its parameters; this function is the only place that
    knows *how* each kind renders as PostgreSQL. See schemas/buildspec.schema.json
    $defs.column_mapping.generator for the shape and required fields per type,
    already enforced by JSON Schema before this ever runs."""
    kind = generator["type"]
    if kind == "ROW_NUMBER":
        # order_by is a bare column name on this buildspec's primary (first-listed)
        # source table -- qualify() resolves it to a fully-qualified FDW reference,
        # matching every other column-level expression this script emits.
        return f"ROW_NUMBER() OVER (ORDER BY {qualify(base_table, generator['order_by'])})"
    if kind == "SEQUENCE":
        return f"nextval('{generator['sequence_name']}')"
    if kind == "UUID":
        # Native to PostgreSQL 13+; no extension required. See docs/ASSUMPTIONS.md
        # "GENERATED columns are a first-class mapping type" for the version note.
        return "gen_random_uuid()"
    if kind == "DEFAULT":
        return generator["default_value"]
    raise ValueError(f"unsupported generator.type '{kind}'")


def build_render_context(spec: dict, intermediate_database: str) -> dict:
    source_tables = spec["source_tables"]
    source_db_by_table = {st["table"]: st["database"] for st in source_tables}

    def source_db_of(table: str) -> str:
        if table not in source_db_by_table:
            raise ValueError(
                f"[{spec['target_table']}] join references table '{table}' that is not "
                f"listed in source_tables. Every table a join touches must appear in "
                f"source_tables so its database (and therefore its FDW alias) is known."
            )
        return source_db_by_table[table]

    columns = spec["columns"]
    needs_review = [c for c in columns if c["transformation"] == "NEEDS_REVIEW"]
    if needs_review:
        names = ", ".join(c["target_column"] for c in needs_review)
        raise ValueError(
            f"[{spec['target_table']}] buildspec still contains NEEDS_REVIEW column(s): "
            f"{names}. The Review plan must fail on these (check C5) before SQLX Generator "
            f"is ever run against this buildspec."
        )

    def qualify(table: str, column: str) -> str:
        """Fully-qualified <fdw_schema>.<table>.<column> reference for a column on a
        table listed in source_tables. Three parts, not two: fdw_alias() returns the
        *schema* the foreign table lives under, not the table itself."""
        return f"{fdw_alias(source_db_of(table))}.{table}.{column}"

    read_columns = []
    for c in columns:
        if c["transformation"] == "LOOKUP":
            continue
        t = c["transformation"]
        if t == "DIRECT":
            src = c["source"]
            if src is None or not isinstance(src["column"], str):
                raise ValueError(
                    f"[{spec['target_table']}.{c['target_column']}] DIRECT transformation "
                    f"requires a single-column source."
                )
            expr = qualify(src["table"], src["column"])
        elif t == "UDF":
            src = c["source"]
            if src is None or c["udf"] is None:
                raise ValueError(
                    f"[{spec['target_table']}.{c['target_column']}] UDF transformation "
                    f"requires both 'source' and 'udf'."
                )
            cols = src["column"] if isinstance(src["column"], list) else [src["column"]]
            args = ", ".join(qualify(src["table"], col) for col in cols)
            expr = f"{c['udf']}({args})"
        elif t in ("EXPRESSION", "CONSTANT"):
            if not c["expression"]:
                raise ValueError(
                    f"[{spec['target_table']}.{c['target_column']}] {t} transformation "
                    f"requires a non-empty 'expression'."
                )
            expr = c["expression"]
        elif t == "GENERATED":
            if not c["generator"]:
                raise ValueError(
                    f"[{spec['target_table']}.{c['target_column']}] GENERATED transformation "
                    f"requires a non-null 'generator'."
                )
            expr = render_generator_expression(c["generator"], qualify, base_table=source_tables[0]["table"])
        else:
            raise ValueError(
                f"[{spec['target_table']}.{c['target_column']}] unsupported transformation "
                f"'{t}'."
            )
        read_columns.append({"target_column": c["target_column"], "read_expr": expr})

    # A LOOKUP column resolves in process.sqlx, against data this table's staging row
    # doesn't otherwise carry (the staging table is shaped like the *target*, not the
    # source). If the LOOKUP declares a natural-key `source`, that natural key must be
    # landed into staging at read time so process.sqlx's UPDATE has something to
    # correlate against. Landed under `_lookup_<target_column>` (see
    # references/naming-conventions.md) -- a helper column, never selected by
    # write.sqlx, which only ever reads the final `columns` list.
    lookup_columns = []
    lookup_helper_columns = []
    for c in columns:
        if c["transformation"] != "LOOKUP":
            continue
        if not c["expression"]:
            raise ValueError(
                f"[{spec['target_table']}.{c['target_column']}] LOOKUP transformation "
                f"requires a non-empty 'expression'."
            )
        lookup_columns.append({"target_column": c["target_column"], "expression": c["expression"]})
        if c["source"] is not None:
            if isinstance(c["source"]["column"], list):
                raise ValueError(
                    f"[{spec['target_table']}.{c['target_column']}] LOOKUP 'source' must be a "
                    f"single natural-key column, not a list."
                )
            lookup_helper_columns.append({
                "helper_column": f"_lookup_{c['target_column']}",
                "type": c["type"],
                "read_expr": qualify(c["source"]["table"], c["source"]["column"]),
            })

    base = source_tables[0]

    # CREATE TABLE needs every final target column plus any lookup helper columns.
    # INSERT/SELECT (read_columns) needs every non-LOOKUP target column plus those
    # same helper columns, landed under their own alias.
    staging_columns = [{"name": c["target_column"], "type": c["type"]} for c in columns] + [
        {"name": h["helper_column"], "type": h["type"]} for h in lookup_helper_columns
    ]
    read_columns = read_columns + [
        {"target_column": h["helper_column"], "read_expr": h["read_expr"]} for h in lookup_helper_columns
    ]

    # Comma-separated column lists are pre-joined here rather than looped over in
    # the template with a trailing "if not loop.last". Jinja2's trim_blocks (used by
    # every template in this skill for otherwise-clean output) strips the newline
    # immediately after ANY block tag, including endif -- so a loop that ends each
    # line with an if/endif comma silently collapses every line onto one. Building
    # the string here sidesteps that whitespace-control trap entirely.
    staging_ddl = ",\n".join(f"    {c['name']} {c['type']}" for c in staging_columns)
    insert_column_list = ",\n".join(f"    {c['target_column']}" for c in read_columns)
    select_expr_list = ",\n".join(f"    {c['read_expr']} AS {c['target_column']}" for c in read_columns)
    target_column_list = ",\n".join(f"    {c['target_column']}" for c in columns)

    return {
        "target_table": spec["target_table"],
        "target_database": spec["target_database"],
        "load_strategy": spec["load_strategy"],
        "staging_table": spec["staging_table"],
        "grain": spec["grain"],
        "mapping_refs": spec["mapping_refs"],
        # Canonical project-relative path per references/naming-conventions.md, not the
        # literal filesystem path this script was invoked with (which may be a temp/test
        # path) -- this is what the engine's config block records and resolves against.
        "buildspec_path": f"metadata/build/{spec['target_table']}.buildspec.json",
        "sqlx_version": SQLX_VERSION,
        "columns": columns,
        "joins": spec["joins"],
        "filters": spec["filters"],
        "source_tables": source_tables,
        "intermediate_database": intermediate_database,
        "staging_ddl": staging_ddl,
        "insert_column_list": insert_column_list,
        "select_expr_list": select_expr_list,
        "target_column_list": target_column_list,
        "lookup_columns": lookup_columns,
        "base_from": f"{fdw_alias(base['database'])}.{base['table']}",
        "fdw_alias": fdw_alias,
        "source_db_of": source_db_of,
    }


def render_table(spec: dict, env: Environment, output_dir: Path, intermediate_database: str) -> list[dict]:
    if spec["load_strategy"] not in SUPPORTED_LOAD_STRATEGIES:
        raise ValueError(
            f"[{spec['target_table']}] load_strategy '{spec['load_strategy']}' has no SQLX "
            f"template yet (supported: {sorted(SUPPORTED_LOAD_STRATEGIES)}). This buildspec "
            f"value is reserved by schemas/buildspec.schema.json for future use per "
            f"ADR-001 §11 -- add templates/sqlx/*.{spec['load_strategy']}.tmpl before using it."
        )

    context = build_render_context(spec, intermediate_database)
    table_dir = output_dir / spec["target_table"]
    table_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for stage in ("read", "process", "write"):
        template = env.get_template(f"{stage}.sqlx.tmpl")
        rendered = template.render(**context)
        out_path = table_dir / f"{stage}.sqlx"
        out_path.write_text(rendered, encoding="utf-8", newline="\n")
        written.append({"path": str(out_path.as_posix()), "hash": sha256_of(out_path)})
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "buildspec_path", type=Path, help="A single *.buildspec.json file or a directory of them"
    )
    parser.add_argument("--templates-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="definitions/ directory")
    parser.add_argument("--schema", type=Path, required=True, help="buildspec.schema.json path")
    parser.add_argument("--intermediate-database", default="intermediate_db")
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))

    if args.buildspec_path.is_dir():
        spec_files = sorted(args.buildspec_path.glob("*.buildspec.json"))
    else:
        spec_files = [args.buildspec_path]

    if not spec_files:
        print(f"ERROR: no buildspec files found at {args.buildspec_path}", file=sys.stderr)
        return 2

    env = Environment(
        loader=FileSystemLoader(str(args.templates_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    all_written: list[dict] = []
    for spec_file in spec_files:
        try:
            spec = load_buildspec(spec_file, schema)
        except jsonschema.exceptions.ValidationError as exc:
            print(f"ERROR: {spec_file} failed buildspec schema validation: {exc.message}", file=sys.stderr)
            return 2
        try:
            all_written.extend(render_table(spec, env, args.output_dir, args.intermediate_database))
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3 if "load_strategy" in str(exc) else 4

    print(json.dumps(all_written, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
