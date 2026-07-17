#!/usr/bin/env python3
"""
Deterministic bootstrap/ generator.

Owned by the Artifact Generator specialist (see specialists/artifact-generator.md), which
runs it as part of Generate. Everything this script emits is a mechanical projection of
the schema IR (metadata/schema/*.json) -- table and column structure only. It NEVER
fabricates row-level sample data (ADR-001 §5/§9): seed files come out as stubs with
column-name scaffolding and explicit TODO markers, nothing else.

Emits, under --output-dir (bootstrap/):
  db/01_init/01_create_schemas.sql
  db/01_init/02_create_fdw_intermediate_to_source.sql   (per declared source database)
  db/01_init/03_create_fdw_target_to_intermediate.sql
  db/01_init/04_create_fdw_intermediate_to_target.sql   (fdw_<target_db> bridge for LOOKUP columns)
  db/02_source/ddl_source_tables.sql
  db/02_source/seed_source_data.sql
  db/03_intermediate/init_staging_schema.sql
  db/03_intermediate/create_udfs.sql                    (verbatim SQL fenced blocks from udf.md)
  db/04_target/ddl_target_tables.sql
  reset/reset_source.sql
  reset/reset_target.sql
  manifest.json                                          (schemas/bootstrap_manifest.schema.json)

Usage:
    python gen_bootstrap.py \
        --source-schema metadata/schema/source_schema.json \
        --target-schema metadata/schema/target_schema.json \
        --udf-doc <path to udf.md> \
        --templates-dir templates/bootstrap \
        --output-dir bootstrap \
        --intermediate-database intermediate_db \
        --buildspecs-dir metadata/build

--buildspecs-dir is optional. When given (every real Generate run has buildspecs
available by the time this specialist runs -- see specialists/artifact-generator.md),
db/01_init/03_create_fdw_target_to_intermediate.sql is rendered with one explicit
CREATE FOREIGN TABLE per staging table (exact column shape from the buildspec,
including LOOKUP helper columns) instead of the unusable IMPORT FOREIGN SCHEMA
placeholder -- see "Why CREATE FOREIGN TABLE, not IMPORT FOREIGN SCHEMA" below.
When omitted, behavior is unchanged from before (placeholder text), so existing
callers (e.g. smoke_test.py, which intentionally exercises this script in isolation
without a buildspecs dir) keep working exactly as before.

## Why CREATE FOREIGN TABLE, not IMPORT FOREIGN SCHEMA, for the staging bridge

Staging tables (stg_<table>) are created at pipeline run time by each table's
read.sqlx, not by bootstrap -- they don't exist yet when this script's output runs.
IMPORT FOREIGN SCHEMA introspects the remote catalog immediately and fails if the
remote table isn't there yet. CREATE FOREIGN TABLE only registers local metadata
and does not validate the remote table until it is actually queried (verified
empirically against a live PostgreSQL 17 instance while building this fix), so
declaring the staging bridge's foreign tables explicitly -- using the same column
shape the buildspec already commits to -- sidesteps the ordering problem entirely.

Exit codes:
    0  success
    2  a schema IR file is missing a field this script needs
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
except ImportError:
    print("ERROR: jinja2 is required. Install with: pip install jinja2", file=sys.stderr)
    sys.exit(1)


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def fdw_alias(database: str) -> str:
    return f"fdw_{database}"


def enrich_tables(schema_ir: dict) -> list[dict]:
    """Add primary_key_columns / foreign_keys derived views, and a pre-joined
    ddl_body string, to each table -- computed purely from the columns already
    present in the schema IR, no new information. ddl_body is built here rather
    than with a comma-chaining Jinja loop for the same reason render_sqlx.py
    pre-joins its column lists: Jinja2's trim_blocks strips the newline after
    every block tag, including endif, so a loop ending each line in
    "{% if not loop.last %},{% endif %}" silently collapses onto one line."""
    enriched = []
    for table in schema_ir["tables"]:
        pk_columns = [c["name"] for c in table["columns"] if c["primary_key"]]
        foreign_keys = [
            {
                "column": c["name"],
                "references_table": c["foreign_key"]["table"],
                "references_column": c["foreign_key"]["column"],
            }
            for c in table["columns"]
            if c["foreign_key"] is not None
        ]

        lines = [
            f"    {c['name']} {c['type']}" + ("" if c["nullable"] else " NOT NULL")
            for c in table["columns"]
        ]
        if pk_columns:
            lines.append(f"    CONSTRAINT {table['name']}_pk PRIMARY KEY ({', '.join(pk_columns)})")
        for fk in foreign_keys:
            lines.append(
                f"    CONSTRAINT {table['name']}_{fk['column']}_fk FOREIGN KEY ({fk['column']}) "
                f"REFERENCES {fk['references_table']} ({fk['references_column']})"
            )
        ddl_body = ",\n".join(lines)

        enriched.append({
            **table,
            "primary_key_columns": pk_columns,
            "foreign_keys": foreign_keys,
            "ddl_body": ddl_body,
        })
    return enriched


def topological_reset_order(tables: list[dict]) -> list[str]:
    """Children (tables with FKs) before parents, so a plain TRUNCATE (without needing
    CASCADE to do the ordering work) still reads top-to-bottom in dependency order.
    Kahn's algorithm over the in-schema FK edges only; a FK to a table outside this
    schema file is not a same-file ordering constraint and is ignored here."""
    names = [t["name"] for t in tables]
    name_set = set(names)
    depends_on: dict[str, set] = {n: set() for n in names}  # child -> parents it references
    for t in tables:
        for fk in t["foreign_keys"]:
            if fk["references_table"] in name_set and fk["references_table"] != t["name"]:
                depends_on[t["name"]].add(fk["references_table"])

    ordered: list[str] = []
    remaining = set(names)
    while remaining:
        # children ready to truncate: everything they depend on is already ordered
        ready = sorted(n for n in remaining if depends_on[n] <= set(ordered))
        if not ready:
            # cycle guard: shouldn't happen for well-formed FKs, but never hang
            ready = sorted(remaining)
        for n in ready:
            ordered.append(n)
            remaining.discard(n)
    return ordered


def foreign_table_shape(table: dict) -> dict:
    """Column-only DDL body for a CREATE FOREIGN TABLE statement: name/type/NOT
    NULL, no CONSTRAINT clauses. PostgreSQL rejects PRIMARY KEY/FOREIGN KEY
    constraints on foreign tables outright (verified against a live PostgreSQL
    17 instance while building this fix: 'primary key constraints are not
    supported on foreign tables') -- table['ddl_body'] from enrich_tables()
    includes exactly those constraints, so it must not be reused here.

    Name is lowercased -- verified against a live PostgreSQL 17 instance that
    this is load-bearing, not cosmetic: db/04_target/ddl_target_tables.sql
    creates tables with an *unquoted* identifier (e.g. `CREATE TABLE DIM_PATIENT`),
    which PostgreSQL folds to lowercase (`dim_patient`) in its catalog regardless
    of how the schema IR spells the name. The FDW `OPTIONS (table_name '...')`
    value is a string literal compared verbatim against that catalog entry, not
    an identifier subject to the same folding -- passing the schema IR's name
    unlowercased here caused a live 'relation does not exist' failure at query
    time even though CREATE FOREIGN TABLE itself succeeded. The Mapping Resolver
    already assumes this convention when it writes a LOOKUP expression like
    `fdw_target_db.dim_patient` (see references/naming-conventions.md), so the
    local foreign table name must match that lowercase spelling too."""
    lines = [
        f"    {c['name']} {c['type']}" + ("" if c["nullable"] else " NOT NULL")
        for c in table["columns"]
    ]
    return {"name": table["name"].lower(), "ddl_body": ",\n".join(lines)}


def staging_table_shape(buildspec: dict) -> dict:
    """The exact column shape (name, type) of one buildspec's staging table --
    every target column plus, for each LOOKUP column with a natural-key source,
    its `_lookup_<target_column>` helper column. This mirrors
    scripts/render_sqlx.py's build_render_context (the only other place this
    shape is computed) rather than importing it: SQLX Generator and this
    specialist's script are deliberately decoupled (each takes only the narrow
    input its own contract names), and this projection is ~10 lines, not worth
    coupling two independently-run scripts over."""
    columns = buildspec["columns"]
    lines = [f"    {c['target_column']} {c['type']}" for c in columns]
    for c in columns:
        if c["transformation"] == "LOOKUP" and c["source"] is not None:
            lines.append(f"    _lookup_{c['target_column']} {c['type']}")
    # Lowercased for the same reason as foreign_table_shape() above: read.sqlx's
    # `CREATE TABLE IF NOT EXISTS {{ staging_table }}` is unquoted, so the real
    # catalog name is always lowercase regardless of the buildspec's own casing
    # (staging_table is conventionally already lowercase, but not schema-enforced).
    return {"name": buildspec["staging_table"].lower(), "ddl_body": ",\n".join(lines)}


def extract_udf_sql_blocks(udf_doc_path: Path) -> list[str]:
    """Pull every fenced ```sql code block out of udf.md verbatim. This is a copy, not a
    parse: the Artifact Generator does not interpret or rewrite UDF bodies, per ADR-001's
    'rendering must never re-derive semantic meaning'. The UDF author's own SQL is the
    only source of truth for the UDF's implementation."""
    text = udf_doc_path.read_text(encoding="utf-8")
    blocks = re.findall(r"```sql\s*\n(.*?)```", text, flags=re.DOTALL)
    return [b.strip() for b in blocks if b.strip()]


def render_and_write(env: Environment, template_name: str, context: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(env.get_template(template_name).render(**context), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-schema", type=Path, required=True)
    parser.add_argument("--target-schema", type=Path, required=True)
    parser.add_argument("--udf-doc", type=Path, required=True)
    parser.add_argument("--templates-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--intermediate-database", default="intermediate_db")
    parser.add_argument("--project-name", default="generated-etl-project")
    parser.add_argument(
        "--buildspecs-dir", type=Path, default=None,
        help="metadata/build/ -- optional; when given, renders the target-to-intermediate "
             "FDW bridge with real staging-table shapes instead of a placeholder (see module "
             "docstring 'Why CREATE FOREIGN TABLE, not IMPORT FOREIGN SCHEMA')",
    )
    args = parser.parse_args()

    source_ir = json.loads(args.source_schema.read_text(encoding="utf-8"))
    target_ir = json.loads(args.target_schema.read_text(encoding="utf-8"))

    source_tables = enrich_tables(source_ir)
    target_tables = enrich_tables(target_ir)

    env = Environment(
        loader=FileSystemLoader(str(args.templates_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    out = args.output_dir
    manifest_objects = []

    # db/02_source
    render_and_write(
        env, "ddl.sql.tmpl",
        {"database": source_ir["database"], "schema_source": args.source_schema.name, "tables": source_tables},
        out / "db" / "02_source" / "ddl_source_tables.sql",
    )
    render_and_write(
        env, "seed_stub.sql.tmpl",
        {"database": source_ir["database"], "schema_source": args.source_schema.name, "tables": source_tables},
        out / "db" / "02_source" / "seed_source_data.sql",
    )
    for t in source_tables:
        manifest_objects.append({
            "database": source_ir["database"], "object": t["name"], "type": "table",
            "script": "bootstrap/db/02_source/ddl_source_tables.sql",
            "command": f"TRUNCATE TABLE {t['name']} CASCADE;",
        })

    # db/04_target
    render_and_write(
        env, "ddl.sql.tmpl",
        {"database": target_ir["database"], "schema_source": args.target_schema.name, "tables": target_tables},
        out / "db" / "04_target" / "ddl_target_tables.sql",
    )
    for t in target_tables:
        manifest_objects.append({
            "database": target_ir["database"], "object": t["name"], "type": "table",
            "script": "bootstrap/db/04_target/ddl_target_tables.sql",
            "command": f"TRUNCATE TABLE {t['name']} CASCADE;",
        })

    # reset/
    render_and_write(
        env, "reset.sql.tmpl",
        {"database": source_ir["database"], "schema_source": args.source_schema.name,
         "reset_order": topological_reset_order(source_tables)},
        out / "reset" / "reset_source.sql",
    )
    render_and_write(
        env, "reset.sql.tmpl",
        {"database": target_ir["database"], "schema_source": args.target_schema.name,
         "reset_order": topological_reset_order(target_tables)},
        out / "reset" / "reset_target.sql",
    )

    # db/01_init
    schemas_sql = "\n".join(
        f"-- {db}: run against that database\nCREATE SCHEMA IF NOT EXISTS public;\n"
        for db in [source_ir["database"], args.intermediate_database, target_ir["database"]]
    )
    init_dir = out / "db" / "01_init"
    init_dir.mkdir(parents=True, exist_ok=True)
    (init_dir / "01_create_schemas.sql").write_text(
        "-- Generated by sqlx-etl-generator · DO NOT EDIT BY HAND\n"
        "-- Ensures the default working schema exists in each database before DDL runs.\n\n"
        + schemas_sql,
        encoding="utf-8", newline="\n",
    )

    render_and_write(
        env, "fdw.sql.tmpl",
        {
            "local_database": args.intermediate_database,
            "remote_database": source_ir["database"],
            "foreign_schema": fdw_alias(source_ir["database"]),
            "server_name": f"{fdw_alias(source_ir['database'])}_srv",
            "tables": [t["name"] for t in source_tables],
            "script_name": "02_create_fdw_intermediate_to_source.sql",
        },
        init_dir / "02_create_fdw_intermediate_to_source.sql",
    )
    if args.buildspecs_dir is not None and args.buildspecs_dir.exists():
        buildspecs = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(args.buildspecs_dir.glob("*.buildspec.json"))
        ]
        staging_tables = [staging_table_shape(b) for b in buildspecs]
        render_and_write(
            env, "fdw_explicit.sql.tmpl",
            {
                "local_database": target_ir["database"],
                "remote_database": args.intermediate_database,
                "foreign_schema": fdw_alias(args.intermediate_database),
                "server_name": f"{fdw_alias(args.intermediate_database)}_srv",
                "tables": staging_tables,
                "script_name": "03_create_fdw_target_to_intermediate.sql",
            },
            init_dir / "03_create_fdw_target_to_intermediate.sql",
        )
    else:
        # Backward-compatible fallback (no buildspecs available -- e.g. smoke_test.py
        # exercising this script in isolation): unusable-as-SQL placeholder text, same
        # as before this fix. A real Generate run always passes --buildspecs-dir.
        render_and_write(
            env, "fdw.sql.tmpl",
            {
                "local_database": target_ir["database"],
                "remote_database": args.intermediate_database,
                "foreign_schema": fdw_alias(args.intermediate_database),
                "server_name": f"{fdw_alias(args.intermediate_database)}_srv",
                "tables": ["<staging tables are named per metadata/build/*.buildspec.json:staging_table -- import per-table after Generate runs, e.g. IMPORT FOREIGN SCHEMA public LIMIT TO (stg_...) ...>"],
                "script_name": "03_create_fdw_target_to_intermediate.sql",
            },
            init_dir / "03_create_fdw_target_to_intermediate.sql",
        )

    # fdw_<target_db>: read target_db from intermediate_db -- needed by process.sqlx's
    # LOOKUP-typed columns (references/naming-conventions.md "Foreign schema alias"),
    # which run in intermediate_db but must read an already-loaded dimension table in
    # target_db. Target tables already exist by bootstrap DDL (04_target, above) before
    # any pipeline run, so this uses the same explicit-CREATE-FOREIGN-TABLE approach for
    # consistency, but would be equally safe with IMPORT FOREIGN SCHEMA.
    render_and_write(
        env, "fdw_explicit.sql.tmpl",
        {
            "local_database": args.intermediate_database,
            "remote_database": target_ir["database"],
            "foreign_schema": fdw_alias(target_ir["database"]),
            "server_name": f"{fdw_alias(target_ir['database'])}_srv",
            "tables": [foreign_table_shape(t) for t in target_tables],
            "script_name": "04_create_fdw_intermediate_to_target.sql",
        },
        init_dir / "04_create_fdw_intermediate_to_target.sql",
    )

    # db/03_intermediate
    intermediate_dir = out / "db" / "03_intermediate"
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    (intermediate_dir / "init_staging_schema.sql").write_text(
        "-- Generated by sqlx-etl-generator · DO NOT EDIT BY HAND\n"
        f"-- Run against: {args.intermediate_database}\n"
        "-- Staging tables themselves are created by each table's read.sqlx at run time\n"
        "-- (CREATE TABLE IF NOT EXISTS), not here -- this script only prepares the namespace.\n\n"
        "CREATE SCHEMA IF NOT EXISTS public;\n",
        encoding="utf-8", newline="\n",
    )

    udf_blocks = extract_udf_sql_blocks(args.udf_doc)
    if udf_blocks:
        udf_header = (
            "-- Generated by sqlx-etl-generator · DO NOT EDIT BY HAND\n"
            f"-- Run against: {args.intermediate_database}\n"
            f"-- UDF bodies copied verbatim from {args.udf_doc.name} -- {len(udf_blocks)} block(s) found.\n"
            "-- This is a copy, not a re-implementation: the source document is authoritative.\n\n"
        )
    else:
        # No fenced ```sql blocks in udf.md -- it declared UDF signatures only,
        # not implementations. This is valid (a buildspec only needs a UDF's
        # name to reference it), but it means the generated pipeline WILL fail
        # at execution time on any UDF call, since nothing creates the function.
        # Never fabricate a body -- surface this loudly instead, both here and
        # on stderr, so it isn't discovered only when Execute (or the engine)
        # hits an undefined-function error against a live database.
        print(
            f"WARNING: no UDF implementation(s) found in {args.udf_doc} -- it declares "
            f"signature(s) only, no fenced ```sql CREATE FUNCTION block(s). "
            f"bootstrap/db/03_intermediate/create_udfs.sql will be empty. Any buildspec "
            f"column with transformation UDF will fail at execution time until real "
            f"implementations are added to that document and Generate is re-run.",
            file=sys.stderr,
        )
        udf_header = (
            "-- Generated by sqlx-etl-generator · DO NOT EDIT BY HAND\n"
            f"-- Run against: {args.intermediate_database}\n"
            f"-- WARNING: 0 UDF block(s) found in {args.udf_doc.name} -- it declares signature(s)\n"
            "-- only, no fenced ```sql CREATE FUNCTION block(s). This file is intentionally\n"
            "-- empty (the generator never fabricates SQL) but any pipeline column using a\n"
            "-- UDF transformation WILL fail at execution time until real implementations are\n"
            "-- added to the UDF document and Generate is re-run.\n\n"
        )
    udf_sql = udf_header + "\n\n".join(udf_blocks) + ("\n" if udf_blocks else "")
    (intermediate_dir / "create_udfs.sql").write_text(udf_sql, encoding="utf-8", newline="\n")

    # manifest.json
    manifest = {"generated_at": now_iso(), "objects": manifest_objects}
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")

    # README.md
    render_and_write(
        env, "README.md.tmpl",
        {
            "project_name": args.project_name,
            "source_database": source_ir["database"],
            "intermediate_database": args.intermediate_database,
            "target_database": target_ir["database"],
            "tables": [t["name"] for t in source_tables] + [t["name"] for t in target_tables],
        },
        out / "README.md",
    )

    print(f"Bootstrap generated at {out} ({len(manifest_objects)} tracked object(s), {len(udf_blocks)} UDF block(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
