"""Normalize correspondence single-column indexes.

Revision ID: 20260211_0003
Revises: 20260210_0002
Create Date: 2026-02-11 21:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260211_0003"
down_revision = "20260210_0002"
branch_labels = None
depends_on = None


def _quoted(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _index_columns(conn: sa.Connection, table_name: str) -> dict[str, tuple[str, ...]]:
    inspector = sa.inspect(conn)
    result: dict[str, tuple[str, ...]] = {}
    for index in inspector.get_indexes(table_name):
        name = str(index.get("name") or "").strip()
        if not name:
            continue
        columns = tuple(str(col) for col in (index.get("column_names") or []))
        result[name] = columns
    return result


def _drop_index_if_exists(conn: sa.Connection, dialect_name: str, index_name: str, table_name: str) -> None:
    if dialect_name in {"postgresql", "sqlite"}:
        conn.execute(sa.text(f"DROP INDEX IF EXISTS {_quoted(index_name)}"))
        return
    op.drop_index(index_name, table_name=table_name)


def _create_index_if_missing(
    conn: sa.Connection,
    dialect_name: str,
    index_name: str,
    table_name: str,
    column_name: str,
) -> None:
    if dialect_name in {"postgresql", "sqlite"}:
        conn.execute(
            sa.text(
                f"CREATE INDEX IF NOT EXISTS {_quoted(index_name)} "
                f"ON {_quoted(table_name)} ({_quoted(column_name)})"
            )
        )
        return
    op.create_index(index_name, table_name, [column_name], unique=False)


def _ensure_single_column_index(conn: sa.Connection, dialect_name: str, table_name: str, index_name: str, column_name: str) -> None:
    existing = _index_columns(conn, table_name)
    current_cols = existing.get(index_name)
    expected_cols = (column_name,)
    if current_cols == expected_cols:
        return
    if current_cols is not None:
        _drop_index_if_exists(conn, dialect_name, index_name, table_name)
    _create_index_if_missing(conn, dialect_name, index_name, table_name, column_name)


def upgrade() -> None:
    conn = op.get_bind()
    dialect_name = conn.dialect.name
    inspector = sa.inspect(conn)
    if "correspondences" not in inspector.get_table_names():
        return

    _ensure_single_column_index(
        conn,
        dialect_name,
        table_name="correspondences",
        index_name="ix_correspondences_issuing_code",
        column_name="issuing_code",
    )
    _ensure_single_column_index(
        conn,
        dialect_name,
        table_name="correspondences",
        index_name="ix_correspondences_category_code",
        column_name="category_code",
    )


def downgrade() -> None:
    conn = op.get_bind()
    dialect_name = conn.dialect.name
    inspector = sa.inspect(conn)
    if "correspondences" not in inspector.get_table_names():
        return

    _drop_index_if_exists(conn, dialect_name, "ix_correspondences_issuing_code", "correspondences")
    _drop_index_if_exists(conn, dialect_name, "ix_correspondences_category_code", "correspondences")
