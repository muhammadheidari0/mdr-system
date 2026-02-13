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


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _serialize_column(col: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": col.get("name"),
        "type": str(col.get("type")),
        "nullable": bool(col.get("nullable")),
        "default": str(col.get("default")) if col.get("default") is not None else None,
    }


def build_report(database_url: str) -> dict[str, Any]:
    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    tables = sorted(inspector.get_table_names())
    report: dict[str, Any] = {
        "generated_at_utc": now,
        "database_url": database_url,
        "dialect": engine.dialect.name,
        "table_count": len(tables),
        "tables": {},
    }

    with engine.connect() as conn:
        for table_name in tables:
            count = conn.execute(sa.text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one()
            columns = inspector.get_columns(table_name)
            indexes = inspector.get_indexes(table_name)
            uniques = inspector.get_unique_constraints(table_name)
            fks = inspector.get_foreign_keys(table_name)
            report["tables"][table_name] = {
                "row_count": int(count),
                "columns": [_serialize_column(col) for col in columns],
                "indexes": _json_safe(indexes),
                "unique_constraints": _json_safe(uniques),
                "foreign_keys": _json_safe(fks),
            }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate DB schema + row-count baseline report.")
    parser.add_argument(
        "--database-url",
        default=settings.DATABASE_URL,
        help="Database URL to inspect (default: app setting DATABASE_URL)",
    )
    parser.add_argument(
        "--out",
        default="reports/db_baseline_report.json",
        help="Output JSON file path",
    )
    args = parser.parse_args()

    database_url = normalize_database_url(args.database_url)
    report = build_report(database_url)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] Baseline report written: {out_path}")


if __name__ == "__main__":
    main()
