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
from app.db.base import Base
from app.db.url_utils import normalize_database_url

# Ensure metadata is populated.
import app.db.models  # noqa: F401

DEFAULT_IGNORED_TABLES = {"alembic_version", "sqlite_sequence"}


def build_drift_report(database_url: str, ignored_tables: set[str] | None = None) -> dict[str, Any]:
    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    ignored = {str(name).strip() for name in (ignored_tables or set()) if str(name).strip()}

    db_tables = {name for name in inspector.get_table_names() if name not in ignored}
    model_tables = {name for name in Base.metadata.tables.keys() if name not in ignored}

    missing_tables = sorted(model_tables - db_tables)
    extra_tables = sorted(db_tables - model_tables)

    column_mismatches: list[dict[str, Any]] = []
    for table_name in sorted(model_tables & db_tables):
        db_cols = {c["name"]: c for c in inspector.get_columns(table_name)}
        model_cols = {c.name: c for c in Base.metadata.tables[table_name].columns}

        missing_columns = sorted(set(model_cols) - set(db_cols))
        extra_columns = sorted(set(db_cols) - set(model_cols))
        for col_name in missing_columns:
            column_mismatches.append(
                {
                    "table": table_name,
                    "column": col_name,
                    "kind": "missing_in_db",
                }
            )
        for col_name in extra_columns:
            column_mismatches.append(
                {
                    "table": table_name,
                    "column": col_name,
                    "kind": "extra_in_db",
                }
            )

        for col_name in sorted(set(model_cols) & set(db_cols)):
            model_col = model_cols[col_name]
            db_col = db_cols[col_name]
            model_nullable = bool(model_col.nullable)
            db_nullable = bool(db_col.get("nullable"))
            if model_nullable != db_nullable:
                column_mismatches.append(
                    {
                        "table": table_name,
                        "column": col_name,
                        "kind": "nullable_drift",
                        "model_nullable": model_nullable,
                        "db_nullable": db_nullable,
                    }
                )

    severity = "ok"
    if missing_tables or any(m["kind"] == "missing_in_db" for m in column_mismatches):
        severity = "critical"
    elif column_mismatches or extra_tables:
        severity = "warning"

    report = {
        "generated_at_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "database_url": database_url,
        "dialect": engine.dialect.name,
        "ignored_tables": sorted(ignored),
        "severity": severity,
        "summary": {
            "missing_tables": len(missing_tables),
            "extra_tables": len(extra_tables),
            "column_mismatches": len(column_mismatches),
        },
        "missing_tables": missing_tables,
        "extra_tables": extra_tables,
        "column_mismatches": column_mismatches,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Report schema drift between SQLAlchemy models and DB.")
    parser.add_argument(
        "--database-url",
        default=settings.DATABASE_URL,
        help="Database URL to inspect (default: app setting DATABASE_URL)",
    )
    parser.add_argument("--out", default="reports/schema_drift_report.json")
    parser.add_argument(
        "--ignore-table",
        action="append",
        default=sorted(DEFAULT_IGNORED_TABLES),
        help="Table name to ignore in drift calculation (repeatable).",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit non-zero on warning/critical drift (default: only critical fails).",
    )
    args = parser.parse_args()

    database_url = normalize_database_url(args.database_url)
    ignored = {str(name).strip() for name in (args.ignore_table or []) if str(name).strip()}
    report = build_drift_report(database_url, ignored_tables=ignored)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] Drift report written: {out_path}")
    print(
        "[summary]",
        f"severity={report['severity']}",
        f"missing_tables={report['summary']['missing_tables']}",
        f"extra_tables={report['summary']['extra_tables']}",
        f"column_mismatches={report['summary']['column_mismatches']}",
    )

    if report["severity"] == "critical":
        raise SystemExit(2)
    if args.fail_on_warning and report["severity"] == "warning":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
