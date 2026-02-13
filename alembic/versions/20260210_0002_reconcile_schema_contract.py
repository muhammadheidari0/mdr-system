"""Reconcile schema contract before PostgreSQL cutover

Revision ID: 20260210_0002
Revises: 20260210_0001
Create Date: 2026-02-10 00:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260210_0002"
down_revision = "20260210_0001"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(str(col.get("name")) == column_name for col in columns)


def _column_nullable(inspector: sa.Inspector, table_name: str, column_name: str) -> bool | None:
    if not _column_exists(inspector, table_name, column_name):
        return None
    for col in inspector.get_columns(table_name):
        if str(col.get("name")) == column_name:
            return bool(col.get("nullable"))
    return None


def _create_reference_no_unique_index(conn: sa.Connection, dialect_name: str) -> None:
    if dialect_name in {"postgresql", "sqlite"}:
        conn.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_correspondences_reference_no "
                "ON correspondences(reference_no) "
                "WHERE reference_no IS NOT NULL"
            )
        )
        return
    op.create_index(
        "uq_correspondences_reference_no",
        "correspondences",
        ["reference_no"],
        unique=True,
    )


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    dialect_name = conn.dialect.name

    if _table_exists(inspector, "issuing_entities"):
        conn.execute(
            sa.text(
                """
                INSERT INTO issuing_entities (code, name_e, project_code, is_active, sort_order)
                SELECT 'G', 'General', NULL, TRUE, 10
                WHERE NOT EXISTS (
                    SELECT 1 FROM issuing_entities WHERE UPPER(code) = UPPER('G')
                )
                """
            )
        )

    if _table_exists(inspector, "correspondence_categories"):
        conn.execute(
            sa.text(
                """
                INSERT INTO correspondence_categories (code, name_e, is_active, sort_order)
                SELECT 'CO', 'Correspondence', TRUE, 10
                WHERE NOT EXISTS (
                    SELECT 1 FROM correspondence_categories WHERE UPPER(code) = UPPER('CO')
                )
                """
            )
        )

    if _table_exists(inspector, "correspondence_attachments"):
        conn.execute(
            sa.text(
                """
                UPDATE correspondence_attachments
                SET file_kind = 'attachment'
                WHERE file_kind IS NULL OR TRIM(file_kind) = ''
                """
            )
        )

    if _table_exists(inspector, "users"):
        conn.execute(
            sa.text(
                """
                UPDATE users
                SET organization_role = 'viewer'
                WHERE organization_role IS NULL OR TRIM(organization_role) = ''
                """
            )
        )

    if _table_exists(inspector, "correspondences"):
        conn.execute(
            sa.text(
                """
                UPDATE correspondences
                SET category_code = 'CO'
                WHERE category_code IS NULL OR TRIM(category_code) = ''
                """
            )
        )
        conn.execute(
            sa.text(
                """
                UPDATE correspondences
                SET issuing_code = COALESCE(NULLIF(TRIM(project_code), ''), 'G')
                WHERE issuing_code IS NULL OR TRIM(issuing_code) = ''
                """
            )
        )
        _create_reference_no_unique_index(conn, dialect_name)

    # Recreate inspector after data normalization and potential index changes.
    inspector = sa.inspect(conn)

    if _column_exists(inspector, "correspondence_attachments", "file_kind"):
        if _column_nullable(inspector, "correspondence_attachments", "file_kind"):
            with op.batch_alter_table("correspondence_attachments") as batch_op:
                batch_op.alter_column(
                    "file_kind",
                    existing_type=sa.String(length=20),
                    nullable=False,
                    existing_server_default=None,
                )

    if _column_exists(inspector, "users", "organization_role"):
        if _column_nullable(inspector, "users", "organization_role"):
            with op.batch_alter_table("users") as batch_op:
                batch_op.alter_column(
                    "organization_role",
                    existing_type=sa.String(length=32),
                    nullable=False,
                    existing_server_default=sa.text("'viewer'"),
                )

    if _column_exists(inspector, "correspondences", "category_code"):
        if _column_nullable(inspector, "correspondences", "category_code"):
            with op.batch_alter_table("correspondences") as batch_op:
                batch_op.alter_column(
                    "category_code",
                    existing_type=sa.String(length=20),
                    nullable=False,
                )

    if _column_exists(inspector, "correspondences", "issuing_code"):
        if _column_nullable(inspector, "correspondences", "issuing_code"):
            with op.batch_alter_table("correspondences") as batch_op:
                batch_op.alter_column(
                    "issuing_code",
                    existing_type=sa.String(length=20),
                    nullable=False,
                )

    if _column_exists(inspector, "correspondences", "project_code"):
        project_nullable = _column_nullable(inspector, "correspondences", "project_code")
        if project_nullable is False:
            with op.batch_alter_table("correspondences") as batch_op:
                batch_op.alter_column(
                    "project_code",
                    existing_type=sa.String(length=50),
                    nullable=True,
                )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if _table_exists(inspector, "correspondences"):
        try:
            op.drop_index("uq_correspondences_reference_no", table_name="correspondences")
        except Exception:
            pass

    if _column_exists(inspector, "correspondence_attachments", "file_kind"):
        if _column_nullable(inspector, "correspondence_attachments", "file_kind") is False:
            with op.batch_alter_table("correspondence_attachments") as batch_op:
                batch_op.alter_column(
                    "file_kind",
                    existing_type=sa.String(length=20),
                    nullable=True,
                )

    if _column_exists(inspector, "users", "organization_role"):
        if _column_nullable(inspector, "users", "organization_role") is False:
            with op.batch_alter_table("users") as batch_op:
                batch_op.alter_column(
                    "organization_role",
                    existing_type=sa.String(length=32),
                    nullable=True,
                )

    if _column_exists(inspector, "correspondences", "category_code"):
        if _column_nullable(inspector, "correspondences", "category_code") is False:
            with op.batch_alter_table("correspondences") as batch_op:
                batch_op.alter_column(
                    "category_code",
                    existing_type=sa.String(length=20),
                    nullable=True,
                )

    if _column_exists(inspector, "correspondences", "issuing_code"):
        if _column_nullable(inspector, "correspondences", "issuing_code") is False:
            with op.batch_alter_table("correspondences") as batch_op:
                batch_op.alter_column(
                    "issuing_code",
                    existing_type=sa.String(length=20),
                    nullable=True,
                )
