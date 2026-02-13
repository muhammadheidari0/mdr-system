from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import sqlalchemy as sa

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.db.url_utils import normalize_database_url

DEFAULT_UNIQUE_CHECKS = [
    "mdr_documents:doc_number",
    "users:email",
    "correspondences:reference_no",
]


def _parse_table_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_unique_checks(raw_values: list[str]) -> dict[str, list[str]]:
    checks: dict[str, list[str]] = {}
    for raw in raw_values:
        if ":" not in raw:
            raise ValueError(f"Invalid unique-check format: {raw!r} (expected table:col[,col])")
        table, cols = raw.split(":", 1)
        table_name = table.strip()
        columns = [c.strip() for c in cols.split(",") if c.strip()]
        if not table_name or not columns:
            raise ValueError(f"Invalid unique-check format: {raw!r}")
        checks[table_name] = columns
    return checks


def _count_rows(conn: sa.Connection, table: sa.Table) -> int:
    return int(conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())


def _duplicate_rows_count(conn: sa.Connection, table: sa.Table, columns: list[str]) -> int:
    cols = [table.c[name] for name in columns]
    grouped = (
        sa.select(*cols, sa.func.count().label("cnt"))
        .select_from(table)
        .group_by(*cols)
        .having(sa.func.count() > 1)
        .subquery()
    )
    return int(conn.execute(sa.select(sa.func.count()).select_from(grouped)).scalar_one())


def _fk_violations_count(conn: sa.Connection, meta: sa.MetaData, table_name: str, fk: dict[str, Any]) -> int:
    local_cols = [str(c) for c in fk.get("constrained_columns") or []]
    ref_table_name = str(fk.get("referred_table") or "")
    ref_cols = [str(c) for c in fk.get("referred_columns") or []]
    if not local_cols or not ref_table_name or not ref_cols or len(local_cols) != len(ref_cols):
        return 0
    if table_name not in meta.tables or ref_table_name not in meta.tables:
        return 0

    local_table = meta.tables[table_name].alias("local_t")
    ref_table = meta.tables[ref_table_name].alias("ref_t")
    join_condition = sa.and_(
        *[local_table.c[local] == ref_table.c[ref] for local, ref in zip(local_cols, ref_cols)]
    )
    non_null_local = sa.and_(*[local_table.c[local].is_not(None) for local in local_cols])
    missing_ref = sa.and_(*[ref_table.c[ref].is_(None) for ref in ref_cols])

    query = (
        sa.select(sa.func.count())
        .select_from(local_table.outerjoin(ref_table, join_condition))
        .where(non_null_local)
        .where(missing_ref)
    )
    return int(conn.execute(query).scalar_one())


def build_parity_report(
    source_url: str,
    target_url: str,
    selected_tables: list[str] | None = None,
    unique_checks: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    source_engine = sa.create_engine(source_url, pool_pre_ping=True)
    try:
        target_engine = sa.create_engine(target_url, pool_pre_ping=True)
    except ModuleNotFoundError as exc:
        if "psycopg" in str(exc):
            raise RuntimeError(
                "Missing PostgreSQL driver `psycopg`. Install dependencies from requirements.txt."
            ) from exc
        raise

    source_meta = sa.MetaData()
    target_meta = sa.MetaData()
    try:
        source_meta.reflect(bind=source_engine)
    except sa.exc.OperationalError as exc:
        raise RuntimeError(
            "Cannot connect to source database. Check --source-url and database availability."
        ) from exc
    try:
        target_meta.reflect(bind=target_engine)
    except sa.exc.OperationalError as exc:
        raise RuntimeError(
            "Cannot connect to target database. Check --target-url and database availability."
        ) from exc

    source_tables = set(source_meta.tables.keys())
    target_tables = set(target_meta.tables.keys())
    common_tables = source_tables & target_tables
    table_names = sorted(common_tables) if not selected_tables else selected_tables

    report: dict[str, Any] = {
        "generated_at_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "source_url": source_url,
        "target_url": target_url,
        "summary": {
            "tables_checked": 0,
            "count_mismatches": 0,
            "unique_issues": 0,
            "fk_violations": 0,
        },
        "tables": {},
    }

    unique_checks = unique_checks or {}
    target_inspector = sa.inspect(target_engine)

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        for table_name in table_names:
            if table_name not in common_tables:
                continue

            source_table = source_meta.tables[table_name]
            target_table = target_meta.tables[table_name]
            source_count = _count_rows(source_conn, source_table)
            target_count = _count_rows(target_conn, target_table)
            count_match = source_count == target_count

            table_unique = unique_checks.get(table_name, [])
            source_duplicates = 0
            target_duplicates = 0
            if table_unique and all(col in source_table.c for col in table_unique) and all(
                col in target_table.c for col in table_unique
            ):
                source_duplicates = _duplicate_rows_count(source_conn, source_table, table_unique)
                target_duplicates = _duplicate_rows_count(target_conn, target_table, table_unique)

            fk_rows: list[dict[str, Any]] = []
            for fk in target_inspector.get_foreign_keys(table_name):
                violations = _fk_violations_count(target_conn, target_meta, table_name, fk)
                if violations > 0:
                    fk_rows.append(
                        {
                            "name": fk.get("name"),
                            "constrained_columns": fk.get("constrained_columns"),
                            "referred_table": fk.get("referred_table"),
                            "referred_columns": fk.get("referred_columns"),
                            "violations": violations,
                        }
                    )

            report["tables"][table_name] = {
                "source_count": source_count,
                "target_count": target_count,
                "count_match": count_match,
                "unique_check_columns": table_unique,
                "source_duplicate_groups": source_duplicates,
                "target_duplicate_groups": target_duplicates,
                "fk_violations": fk_rows,
            }

            report["summary"]["tables_checked"] += 1
            if not count_match:
                report["summary"]["count_mismatches"] += 1
            if source_duplicates or target_duplicates:
                report["summary"]["unique_issues"] += 1
            if fk_rows:
                report["summary"]["fk_violations"] += sum(int(row["violations"]) for row in fk_rows)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare row/unique/FK parity between source and target DB.")
    parser.add_argument("--source-url", default="sqlite:///./database/mdr_project.db")
    parser.add_argument("--target-url", default=settings.DATABASE_URL)
    parser.add_argument("--tables", default="", help="Comma-separated subset of tables")
    parser.add_argument(
        "--unique-check",
        action="append",
        default=[],
        help="Unique check as table:column or table:col1,col2 (repeatable)",
    )
    parser.add_argument("--report", default="reports/data_parity_report.json")
    args = parser.parse_args()

    source_url = normalize_database_url(args.source_url)
    target_url = normalize_database_url(args.target_url)
    selected_tables = _parse_table_list(args.tables)

    raw_unique_checks = args.unique_check[:] if args.unique_check else []
    if not raw_unique_checks:
        raw_unique_checks = DEFAULT_UNIQUE_CHECKS[:]
    unique_checks = _parse_unique_checks(raw_unique_checks)

    try:
        report = build_parity_report(
            source_url=source_url,
            target_url=target_url,
            selected_tables=selected_tables or None,
            unique_checks=unique_checks,
        )
    except Exception as exc:
        print(f"[error] {exc}")
        raise SystemExit(2) from exc

    out_path = Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] Data parity report written: {out_path}")
    print(
        "[summary]",
        f"tables={report['summary']['tables_checked']}",
        f"count_mismatches={report['summary']['count_mismatches']}",
        f"unique_issues={report['summary']['unique_issues']}",
        f"fk_violations={report['summary']['fk_violations']}",
    )


if __name__ == "__main__":
    main()
