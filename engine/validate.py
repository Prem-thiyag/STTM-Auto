"""
Live validation of a generated + executed SQLX ETL project: does what
Generate produced, and what Execute actually loaded, match reality -- schema,
generated artifacts, and data -- end to end? Nothing else in engine/ or the
sqlx-etl-generator skill checks a *live database's* data against what the
pipeline was supposed to produce (executor.py only runs SQL; the skill's
Review plan validates static artifacts and, optionally, live *schema* -- never
data), so this is new capability, not a wrapper around something that already
exists.

Reuses engine.postgres.resolve_connection_config for every database
connection and jsonschema (already a dependency of the skill's own scripts)
to validate buildspecs against the skill's schemas/buildspec.schema.json.
Never re-reads the five original input documents and never re-derives a
mapping decision -- only checks that what Generate already decided is what is
actually there, live.

Every check is driven by declared metadata (source_schema.json /
target_schema.json / buildspec columns), never by a hardcoded table or column
name -- this project's two tables are incidental, not assumed. The one check
that could easily tempt hardcoding a business formula -- "did a UDF
transformation compute the right value" -- is instead answered by
re-invoking the *actual* UDF (already loaded into intermediate_db by
bootstrap) against the same source values via SQL, never by reimplementing
its logic in Python.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from engine.exceptions import EngineError
from engine.models import ConnectionConfig
from engine.postgres import resolve_connection_config

try:
    import psycopg2
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None  # type: ignore[assignment]

DEFAULT_SKILL_ROOT = Path(".claude/skills/sqlx-etl-generator")


@dataclass
class Check:
    id: str
    category: str  # "generation" | "schema" | "data"
    status: str  # "PASS" | "FAIL" | "WARN"
    detail: str


@dataclass
class ValidationReport:
    validated_at: str
    status: str
    checks: list[Check] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "validated_at": self.validated_at,
            "status": self.status,
            "checks": [
                {"id": c.id, "category": c.category, "status": c.status, "detail": c.detail}
                for c in self.checks
            ],
        }


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _pg_type_matches(declared: str, information_schema_row: dict) -> bool:
    """Loose comparison between a schema-IR type string (e.g. 'VARCHAR(200)',
    'BIGINT', 'TIMESTAMP') and what information_schema.columns actually
    reports (data_type + character_maximum_length). Loose on purpose: the
    schema IR records the type as a human wrote it, Postgres normalizes names
    (INT -> integer, VARCHAR -> character varying) -- an exact string compare
    would false-positive on every column."""
    declared_upper = declared.strip().upper()
    base = declared_upper.split("(")[0].strip()
    aliases = {
        "INT": "integer", "INTEGER": "integer", "BIGINT": "bigint", "SMALLINT": "smallint",
        "VARCHAR": "character varying", "CHARACTER VARYING": "character varying", "TEXT": "text",
        "DATE": "date", "TIMESTAMP": "timestamp without time zone", "BOOLEAN": "boolean",
        "NUMERIC": "numeric", "DECIMAL": "numeric",
    }
    expected_data_type = aliases.get(base)
    if expected_data_type is None:
        return True  # unrecognized type spelling -- don't false-fail on something we can't map
    if information_schema_row["data_type"] != expected_data_type:
        return False
    if base in ("VARCHAR", "CHARACTER VARYING") and "(" in declared_upper:
        declared_len = int(declared_upper.split("(")[1].rstrip(")"))
        return information_schema_row["character_maximum_length"] == declared_len
    return True


def validate_generation(project_root: Path, skill_root: Path) -> list[Check]:
    checks: list[Check] = []
    metadata = project_root / "metadata"
    manifest_path = metadata / "manifest.json"

    if not manifest_path.exists():
        return [Check("G0", "generation", "FAIL", f"{manifest_path} not found -- run Generate first.")]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Artifact completeness.
    for table in manifest.get("tables", []):
        for stage in ("read", "process", "write"):
            p = project_root / "definitions" / table / f"{stage}.sqlx"
            checks.append(Check(
                f"G-artifact-{table}-{stage}", "generation",
                "PASS" if p.exists() else "FAIL",
                f"{p} {'exists' if p.exists() else 'is MISSING'}",
            ))
        bs = metadata / "build" / f"{table}.buildspec.json"
        checks.append(Check(
            f"G-buildspec-{table}", "generation",
            "PASS" if bs.exists() else "FAIL",
            f"{bs} {'exists' if bs.exists() else 'is MISSING'}",
        ))

    # Buildspec schema validation.
    schema_path = skill_root / "schemas" / "buildspec.schema.json"
    if jsonschema is not None and schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for bs_path in sorted((metadata / "build").glob("*.buildspec.json")):
            try:
                jsonschema.validate(json.loads(bs_path.read_text(encoding="utf-8")), schema)
                checks.append(Check(f"G-schema-{bs_path.stem}", "generation", "PASS", f"{bs_path} valid"))
            except jsonschema.exceptions.ValidationError as exc:
                checks.append(Check(f"G-schema-{bs_path.stem}", "generation", "FAIL", str(exc.message)))
    else:
        checks.append(Check("G-schema", "generation", "WARN", "jsonschema unavailable or schema file missing -- skipped"))

    # Dependency graph / execution plan consistency.
    dep_path = metadata / "dependency" / "dependency_graph.json"
    plan_path = metadata / "execution" / "execution_plan.json"
    if dep_path.exists() and plan_path.exists():
        dep = json.loads(dep_path.read_text(encoding="utf-8"))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        expected = dep.get("execution_order", [])
        actual = [f"{s['table']}.{s['stage']}" for s in plan.get("steps", [])]
        checks.append(Check(
            "G-dependency-order", "generation",
            "PASS" if expected == actual else "FAIL",
            "execution_plan.json order matches dependency_graph.json execution_order"
            if expected == actual else f"expected {expected}, got {actual}",
        ))
    else:
        checks.append(Check("G-dependency-order", "generation", "FAIL", "dependency_graph.json or execution_plan.json missing"))

    # NEEDS_REVIEW backstop (same rule as the skill's Review C5, re-checked here
    # because Validate must not assume Review was run first).
    needs_review: list[str] = []
    for bs_path in sorted((metadata / "build").glob("*.buildspec.json")):
        bs = json.loads(bs_path.read_text(encoding="utf-8"))
        needs_review += [
            f"{bs['target_table']}.{c['target_column']}" for c in bs["columns"]
            if c["transformation"] == "NEEDS_REVIEW"
        ]
    checks.append(Check(
        "G-no-needs-review", "generation",
        "FAIL" if needs_review else "PASS",
        f"NEEDS_REVIEW column(s) present: {needs_review}" if needs_review else "no NEEDS_REVIEW columns",
    ))

    # Manifest drift.
    drifted = []
    for entry in manifest.get("generated_files", []):
        p = project_root / entry["path"] if not Path(entry["path"]).is_absolute() else Path(entry["path"])
        if not p.exists():
            drifted.append(f"{entry['path']}: missing")
        elif _sha256(p) != entry["hash"]:
            drifted.append(f"{entry['path']}: hash mismatch")
    checks.append(Check(
        "G-manifest-drift", "generation",
        "WARN" if drifted else "PASS",
        "; ".join(drifted) if drifted else "no drift since last Generate",
    ))
    return checks


def validate_schema(label: str, schema_json_path: Path, config: ConnectionConfig) -> list[Check]:
    checks: list[Check] = []
    if not schema_json_path.exists():
        return [Check(f"S-{label}", "schema", "FAIL", f"{schema_json_path} not found")]
    schema_ir = json.loads(schema_json_path.read_text(encoding="utf-8"))

    conn = psycopg2.connect(host=config.host, port=config.port, dbname=config.dbname,
                             user=config.user, password=config.password)
    try:
        with conn.cursor() as cur:
            for table in schema_ir["tables"]:
                cur.execute(
                    "SELECT column_name, data_type, character_maximum_length, is_nullable "
                    "FROM information_schema.columns WHERE lower(table_name) = lower(%s)",
                    (table["name"],),
                )
                rows = {r[0].lower(): {"data_type": r[1], "character_maximum_length": r[2], "is_nullable": r[3]}
                        for r in cur.fetchall()}
                if not rows:
                    checks.append(Check(f"S-{label}-{table['name']}", "schema", "FAIL",
                                         f"table '{table['name']}' not found in live {label} database"))
                    continue
                for col in table["columns"]:
                    live = rows.get(col["name"].lower())
                    if live is None:
                        checks.append(Check(f"S-{label}-{table['name']}.{col['name']}", "schema", "FAIL",
                                             f"column '{col['name']}' missing from live table '{table['name']}'"))
                        continue
                    if not _pg_type_matches(col["type"], live):
                        checks.append(Check(f"S-{label}-{table['name']}.{col['name']}", "schema", "FAIL",
                                             f"type mismatch: declared '{col['type']}', live "
                                             f"'{live['data_type']}'(len={live['character_maximum_length']})"))
                    else:
                        checks.append(Check(f"S-{label}-{table['name']}.{col['name']}", "schema", "PASS",
                                             "matches live schema"))
    finally:
        conn.close()
    return checks


def validate_data(project_root: Path, source: ConnectionConfig, intermediate: ConnectionConfig,
                   target: ConnectionConfig) -> list[Check]:
    checks: list[Check] = []
    target_schema = json.loads((project_root / "metadata/schema/target_schema.json").read_text(encoding="utf-8"))
    tables_by_name = {t["name"]: t for t in target_schema["tables"]}

    build_dir = project_root / "metadata/build"
    buildspecs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(build_dir.glob("*.buildspec.json"))]

    tconn = psycopg2.connect(host=target.host, port=target.port, dbname=target.dbname,
                              user=target.user, password=target.password)
    iconn = psycopg2.connect(host=intermediate.host, port=intermediate.port, dbname=intermediate.dbname,
                              user=intermediate.user, password=intermediate.password)
    sconn = psycopg2.connect(host=source.host, port=source.port, dbname=source.dbname,
                              user=source.user, password=source.password)
    try:
        for bs in buildspecs:
            table = bs["target_table"]
            schema_table = tables_by_name.get(table, {})

            # Row counts: staging (intermediate_db) vs target -- must match exactly under
            # full_load with no declared filters (every staged row is written, unfiltered).
            with iconn.cursor() as cur:
                cur.execute(f'SELECT count(*) FROM {bs["staging_table"]}')
                staging_count = cur.fetchone()[0]
            with tconn.cursor() as cur:
                cur.execute(f'SELECT count(*) FROM {table}')
                target_count = cur.fetchone()[0]
            if bs["filters"]:
                checks.append(Check(f"D-rowcount-{table}", "data", "WARN",
                                     f"staging={staging_count}, target={target_count} "
                                     f"(buildspec declares filter(s), exact match not asserted)"))
            else:
                checks.append(Check(
                    f"D-rowcount-{table}", "data",
                    "PASS" if staging_count == target_count else "FAIL",
                    f"staging={staging_count}, target={target_count}",
                ))

            # Duplicate detection: declared primary key(s) must be unique in the live table.
            pk_cols = [c["name"] for c in schema_table.get("columns", []) if c["primary_key"]]
            if pk_cols and target_count > 0:
                cols = ", ".join(pk_cols)
                with tconn.cursor() as cur:
                    cur.execute(f'SELECT {cols}, count(*) FROM {table} GROUP BY {cols} HAVING count(*) > 1')
                    dups = cur.fetchall()
                checks.append(Check(
                    f"D-duplicates-{table}", "data",
                    "FAIL" if dups else "PASS",
                    f"{len(dups)} duplicate primary-key group(s) on ({cols})" if dups else f"({cols}) unique",
                ))

            # NULL handling: declared NOT NULL columns must have zero NULLs live.
            not_null_cols = [c["name"] for c in schema_table.get("columns", []) if not c["nullable"]]
            for col in not_null_cols:
                with tconn.cursor() as cur:
                    cur.execute(f'SELECT count(*) FROM {table} WHERE {col} IS NULL')
                    n = cur.fetchone()[0]
                checks.append(Check(f"D-notnull-{table}.{col}", "data", "FAIL" if n else "PASS",
                                     f"{n} unexpected NULL(s) in NOT NULL column" if n else "no NULLs"))

            # Referential integrity: declared FK columns must resolve to an existing row
            # in the referenced target table (both live in target_db here).
            for col in schema_table.get("columns", []):
                fk = col.get("foreign_key")
                if not fk:
                    continue
                with tconn.cursor() as cur:
                    cur.execute(
                        f'SELECT count(*) FROM {table} t WHERE t.{col["name"]} IS NOT NULL '
                        f'AND NOT EXISTS (SELECT 1 FROM {fk["table"]} r WHERE r.{fk["column"]} = t.{col["name"]})'
                    )
                    orphans = cur.fetchone()[0]
                checks.append(Check(
                    f"D-fk-{table}.{col['name']}", "data", "FAIL" if orphans else "PASS",
                    f"{orphans} row(s) with {col['name']} not found in {fk['table']}.{fk['column']}"
                    if orphans else f"all {col['name']} values resolve to {fk['table']}.{fk['column']}",
                ))

            # UDF transformation correctness: re-invoke the actual UDF (in intermediate_db)
            # against the same source values, joined via each column's own DIRECT-mapped
            # natural key -- never reimplement the UDF's logic here.
            direct_join_col = next(
                (c for c in bs["columns"]
                 if c["transformation"] == "DIRECT" and c["source"] and not isinstance(c["source"]["column"], list)),
                None,
            )
            udf_cols = [c for c in bs["columns"] if c["transformation"] == "UDF"]
            if udf_cols and direct_join_col is not None:
                base_table = bs["source_tables"][0]["table"]
                src_join_col = direct_join_col["source"]["column"]
                tgt_join_col = direct_join_col["target_column"]
                with sconn.cursor() as cur:
                    cur.execute(f'SELECT * FROM {base_table}')
                    src_cols = [d[0] for d in cur.description]
                    src_rows = {dict(zip(src_cols, row))[src_join_col]: dict(zip(src_cols, row))
                                for row in cur.fetchall()}
                with tconn.cursor() as cur:
                    cur.execute(f'SELECT * FROM {table}')
                    tgt_cols = [d[0] for d in cur.description]
                    tgt_rows = [dict(zip(tgt_cols, row)) for row in cur.fetchall()]

                for c in udf_cols:
                    mismatches = 0
                    checked = 0
                    src_arg_cols = c["source"]["column"] if isinstance(c["source"]["column"], list) else [c["source"]["column"]]
                    for trow in tgt_rows:
                        key = trow.get(tgt_join_col)
                        srow = src_rows.get(key)
                        if srow is None:
                            continue
                        args = [srow.get(col) for col in src_arg_cols]
                        with iconn.cursor() as cur:
                            cur.execute(f'SELECT {c["udf"]}({", ".join(["%s"] * len(args))})', args)
                            expected = cur.fetchone()[0]
                        checked += 1
                        if trow.get(c["target_column"]) != expected:
                            mismatches += 1
                    checks.append(Check(
                        f"D-udf-{table}.{c['target_column']}", "data",
                        "FAIL" if mismatches else ("WARN" if checked == 0 else "PASS"),
                        f"{mismatches}/{checked} row(s) mismatch re-invoking {c['udf']}(...)" if checked
                        else "no rows to check",
                    ))
    finally:
        tconn.close()
        iconn.close()
        sconn.close()
    return checks


def run(project_root: Path, skill_root: Path = DEFAULT_SKILL_ROOT) -> ValidationReport:
    if psycopg2 is None:
        raise EngineError("psycopg2 is not installed. Install with: pip install -r engine/requirements.txt")

    checks = validate_generation(project_root, skill_root)

    source_cfg = resolve_connection_config("source_db")
    intermediate_cfg = resolve_connection_config("intermediate_db")
    target_cfg = resolve_connection_config("target_db")

    checks += validate_schema("source", project_root / "metadata/schema/source_schema.json", source_cfg)
    checks += validate_schema("target", project_root / "metadata/schema/target_schema.json", target_cfg)
    checks += validate_data(project_root, source_cfg, intermediate_cfg, target_cfg)

    if any(c.status == "FAIL" for c in checks):
        status = "FAIL"
    elif any(c.status == "WARN" for c in checks):
        status = "WARN"
    else:
        status = "PASS"
    report = ValidationReport(validated_at=_now_iso(), status=status, checks=checks)

    out_path = project_root / "metadata" / "validate" / "validation_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8", newline="\n")
    return report


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()  # repo-root .env -> os.environ, if present; never overwrites already-set vars
    except ImportError:  # pragma: no cover - exercised only when python-dotenv truly isn't installed
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", nargs="?", default="output", type=Path)
    parser.add_argument("--skill-root", default=DEFAULT_SKILL_ROOT, type=Path)
    args = parser.parse_args()

    try:
        report = run(args.project_root, args.skill_root)
    except EngineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for c in report.checks:
        print(f"[{c.status:<4}] {c.id:<40} {c.detail}")
    print(f"\nOverall: {report.status}")
    return 0 if report.status != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
