from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import sqlalchemy as sa

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.db.url_utils import normalize_database_url

BATCH_SIZE = 1000
DEFAULT_SQLITE_DB_PATH = (PROJECT_ROOT / "database" / "mdr_project.db").resolve()

PREFERRED_LOAD_ORDER = [
    "organizations",
    "users",
    "projects",
    "blocks",
    "phases",
    "disciplines",
    "packages",
    "levels",
    "doc_statuses",
    "mdr_categories",
    "issuing_entities",
    "correspondence_categories",
    "mdr_documents",
    "document_revisions",
    "archive_files",
    "transmittals",
    "transmittal_docs",
    "correspondences",
    "correspondence_actions",
    "correspondence_attachments",
    "workboard_items",
    "settings_kv",
    "settings_audit_logs",
    "role_permissions",
    "role_category_permissions",
    "role_category_project_scopes",
    "role_category_discipline_scopes",
    "role_project_scopes",
    "role_discipline_scopes",
    "user_project_scopes",
    "user_discipline_scopes",
]

SELF_REFERENCE_TWO_PASS = {
    "organizations": "parent_id",
    "archive_files": "companion_file_id",
}


def _parse_table_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _default_sqlite_url() -> str:
    return f"sqlite:///{DEFAULT_SQLITE_DB_PATH.as_posix()}"


def _validate_sqlite_source_exists(sqlite_url: str) -> None:
    try:
        parsed = sa.engine.make_url(sqlite_url)
    except Exception:
        return

    if parsed.get_backend_name() != "sqlite":
        return
    if not parsed.database or parsed.database == ":memory:":
        return

    source_path = Path(parsed.database)
    if not source_path.is_absolute():
        source_path = (Path.cwd() / source_path).resolve()
    if not source_path.exists():
        raise RuntimeError(
            f"SQLite source database not found: {source_path}. "
            "Pass --sqlite-url with a valid source file path."
        )


def _ordered_tables(candidate_tables: Iterable[str]) -> list[str]:
    table_set = set(candidate_tables)
    ordered = [name for name in PREFERRED_LOAD_ORDER if name in table_set]
    ordered.extend(sorted(table_set - set(ordered)))
    return ordered


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {"1", "true", "t", "yes", "y"}:
        return True
    if raw in {"0", "false", "f", "no", "n"}:
        return False
    return None


def _to_datetime(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _to_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    parsed = _to_datetime(value)
    return parsed.date() if parsed else None


def _to_time(value: Any) -> dt.time | None:
    if value is None:
        return None
    if isinstance(value, dt.time):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return dt.time.fromisoformat(raw)
    except Exception:
        parsed = _to_datetime(raw)
        return parsed.time() if parsed else None


def _normalize_value(value: Any, column: sa.Column) -> Any:
    if isinstance(value, str):
        if value == "" and column.nullable:
            return None
        value = value.strip()

    if isinstance(column.type, sa.Boolean):
        bool_value = _to_bool(value)
        if bool_value is not None:
            return bool_value

    if isinstance(column.type, sa.DateTime):
        parsed = _to_datetime(value)
        if parsed is not None:
            return parsed

    if isinstance(column.type, sa.Date):
        parsed = _to_date(value)
        if parsed is not None:
            return parsed

    if isinstance(column.type, sa.Time):
        parsed = _to_time(value)
        if parsed is not None:
            return parsed

    return value


def _quoted(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _maybe_truncate_target(conn: sa.Connection, table_names: list[str]) -> None:
    if not table_names:
        return
    dialect = conn.dialect.name
    if dialect == "postgresql":
        targets = ", ".join(_quoted(name) for name in table_names)
        conn.execute(sa.text(f"TRUNCATE TABLE {targets} RESTART IDENTITY CASCADE"))
        return

    # Generic fallback.
    for table_name in reversed(table_names):
        conn.execute(sa.text(f"DELETE FROM {_quoted(table_name)}"))


def _reset_postgres_sequences(conn: sa.Connection, table: sa.Table) -> None:
    if conn.dialect.name != "postgresql":
        return

    pk_columns = list(table.primary_key.columns)
    if len(pk_columns) != 1:
        return
    pk_col = pk_columns[0]
    if not isinstance(pk_col.type, sa.Integer):
        return

    table_name = table.name
    column_name = pk_col.name
    sql = sa.text(
        f"""
        SELECT setval(
            pg_get_serial_sequence(:table_name, :column_name),
            COALESCE((SELECT MAX({_quoted(column_name)}) FROM {_quoted(table_name)}), 0) + 1,
            false
        )
        """
    )
    try:
        conn.execute(sql, {"table_name": table_name, "column_name": column_name})
    except Exception:
        # Not all integer PKs are backed by a serial/identity sequence.
        pass


def _collect_source_project_codes(
    src_conn: sa.Connection,
    sqlite_meta: sa.MetaData,
) -> set[str]:
    if "projects" not in sqlite_meta.tables:
        return set()

    project_table = sqlite_meta.tables["projects"]
    return {
        str(code).strip()
        for code in src_conn.execute(sa.select(project_table.c.code)).scalars().all()
        if str(code or "").strip()
    }

def _normalize_project_reference(
    payload: dict[str, Any],
    table: sa.Table,
    source_project_codes: set[str],
    table_name: str,
) -> None:
    if "project_code" not in payload:
        return

    raw_code = payload.get("project_code")
    normalized = str(raw_code or "").strip()
    if not normalized:
        payload["project_code"] = None
        return
    if normalized in source_project_codes:
        payload["project_code"] = normalized
        return

    column = table.c.get("project_code")
    if column is not None and column.nullable:
        payload["project_code"] = None
        return

    raise RuntimeError(
        f"Invalid project_code={normalized!r} for non-nullable {table_name}.project_code"
    )


def run_etl(
    sqlite_url: str,
    postgres_url: str,
    selected_tables: list[str] | None = None,
    dry_run: bool = True,
    execute: bool = False,
    truncate_target: bool = False,
) -> dict[str, Any]:
    sqlite_engine = sa.create_engine(sqlite_url, pool_pre_ping=True)
    try:
        postgres_engine = sa.create_engine(postgres_url, pool_pre_ping=True)
    except ModuleNotFoundError as exc:
        if "psycopg" in str(exc):
            raise RuntimeError(
                "Missing PostgreSQL driver `psycopg`. Install dependencies from requirements.txt."
            ) from exc
        raise

    sqlite_meta = sa.MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)
    postgres_meta = sa.MetaData()
    try:
        postgres_meta.reflect(bind=postgres_engine)
    except sa.exc.OperationalError as exc:
        raise RuntimeError(
            "Cannot connect to PostgreSQL target. Ensure the database is up and DATABASE_URL is correct."
        ) from exc

    sqlite_tables = set(sqlite_meta.tables.keys())
    postgres_tables = set(postgres_meta.tables.keys())
    common_tables = sqlite_tables & postgres_tables

    if not sqlite_tables:
        raise RuntimeError(
            "Source SQLite has no tables. Check --sqlite-url and ensure the expected DB file is used."
        )
    if not postgres_tables:
        raise RuntimeError(
            "Target PostgreSQL has no tables. Run `alembic upgrade head` before ETL."
        )
    if not common_tables:
        raise RuntimeError(
            f"No common tables found between source ({len(sqlite_tables)}) and target ({len(postgres_tables)}). "
            "Run migrations on PostgreSQL and verify the SQLite source path."
        )

    requested = selected_tables or []
    if requested:
        unknown = [name for name in requested if name not in common_tables]
        if unknown:
            raise RuntimeError(f"Unknown or unmatched table(s): {unknown}")
        table_names = _ordered_tables(requested)
    else:
        table_names = _ordered_tables(common_tables - {"alembic_version"})

    report: dict[str, Any] = {
        "sqlite_url": sqlite_url,
        "postgres_url": postgres_url,
        "dry_run": dry_run,
        "execute": execute,
        "truncate_target": truncate_target,
        "source_table_count": len(sqlite_tables),
        "target_table_count": len(postgres_tables),
        "common_table_count": len(common_tables),
        "tables": {},
    }

    with sqlite_engine.connect() as src_conn, postgres_engine.begin() as dst_conn:
        source_project_codes = _collect_source_project_codes(src_conn, sqlite_meta)

        if execute and truncate_target:
            _maybe_truncate_target(dst_conn, table_names)

        for table_name in table_names:
            src_table = sqlite_meta.tables[table_name]
            dst_table = postgres_meta.tables[table_name]

            source_count = int(src_conn.execute(sa.select(sa.func.count()).select_from(src_table)).scalar_one())
            target_before = int(dst_conn.execute(sa.select(sa.func.count()).select_from(dst_table)).scalar_one())

            inserted = 0
            patched = 0
            errors: list[str] = []
            patch_rows: list[dict[str, Any]] = []
            ref_column = SELF_REFERENCE_TWO_PASS.get(table_name)
            has_two_pass = bool(ref_column and "id" in src_table.c and ref_column in src_table.c and ref_column in dst_table.c)

            if execute:
                result = src_conn.execute(sa.select(src_table)).mappings()
                while True:
                    batch = result.fetchmany(BATCH_SIZE)
                    if not batch:
                        break

                    transformed: list[dict[str, Any]] = []
                    for row in batch:
                        payload: dict[str, Any] = {}
                        for column in dst_table.columns:
                            if column.name not in row:
                                continue
                            payload[column.name] = _normalize_value(row[column.name], column)
                        _normalize_project_reference(payload, dst_table, source_project_codes, table_name)

                        if has_two_pass and payload.get("id") is not None:
                            ref_value = payload.get(ref_column)
                            if ref_value is not None:
                                patch_rows.append({"id": payload["id"], ref_column: ref_value})
                                payload[ref_column] = None

                        transformed.append(payload)

                    if transformed:
                        try:
                            dst_conn.execute(dst_table.insert(), transformed)
                            inserted += len(transformed)
                        except Exception as exc:
                            errors.append(str(exc))
                            raise

                if has_two_pass and patch_rows:
                    pk_param = "_pk_id"
                    update_stmt = (
                        dst_table.update()
                        .where(dst_table.c.id == sa.bindparam(pk_param))
                        .values({ref_column: sa.bindparam(ref_column)})
                    )
                    patch_payload = [
                        {pk_param: row["id"], ref_column: row[ref_column]}
                        for row in patch_rows
                        if "id" in row
                    ]
                    dst_conn.execute(update_stmt, patch_payload)
                    patched = len(patch_rows)

                _reset_postgres_sequences(dst_conn, dst_table)

            target_after = int(dst_conn.execute(sa.select(sa.func.count()).select_from(dst_table)).scalar_one())
            report["tables"][table_name] = {
                "source_count": source_count,
                "target_count_before": target_before,
                "target_count_after": target_after,
                "inserted": inserted,
                "patched_self_refs": patched,
                "status": "ok" if not errors else "error",
                "errors": errors,
            }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Repeatable ETL from SQLite to PostgreSQL.")
    parser.add_argument(
        "--sqlite-url",
        default=_default_sqlite_url(),
        help="Source SQLite URL",
    )
    parser.add_argument(
        "--postgres-url",
        default=settings.DATABASE_URL,
        help="Target PostgreSQL URL",
    )
    parser.add_argument(
        "--tables",
        default="",
        help="Comma-separated table list (optional). Defaults to all common tables.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only analyze and report; do not write.")
    parser.add_argument("--execute", action="store_true", help="Execute ETL inserts.")
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="Truncate selected target tables before loading.",
    )
    parser.add_argument("--report", default="reports/sqlite_to_postgres_etl_report.json")
    args = parser.parse_args()

    sqlite_url = normalize_database_url(args.sqlite_url)
    postgres_url = normalize_database_url(args.postgres_url)

    dry_run = bool(args.dry_run)
    execute = bool(args.execute)
    if not dry_run and not execute:
        dry_run = True

    if execute and dry_run:
        # If both are given, prioritize execute and still produce full report.
        dry_run = False

    if "sqlite" in postgres_url.lower():
        raise RuntimeError("Target URL must be PostgreSQL, not SQLite.")
    if "sqlite" not in sqlite_url.lower():
        raise RuntimeError("Source URL must be SQLite.")

    _validate_sqlite_source_exists(sqlite_url)

    selected_tables = _parse_table_list(args.tables)
    try:
        report = run_etl(
            sqlite_url=sqlite_url,
            postgres_url=postgres_url,
            selected_tables=selected_tables,
            dry_run=dry_run,
            execute=execute,
            truncate_target=bool(args.truncate_target),
        )
    except Exception as exc:
        print(f"[error] {exc}")
        raise SystemExit(2) from exc

    out_path = Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] ETL report written: {out_path}")
    print(
        "[summary]",
        f"tables={len(report['tables'])}",
        f"mode={'execute' if execute else 'dry-run'}",
    )


if __name__ == "__main__":
    main()
