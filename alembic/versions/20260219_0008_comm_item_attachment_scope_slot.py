"""Add scope/slot context columns for comm item attachments.

Revision ID: 20260219_0008
Revises: 20260218_0007
Create Date: 2026-02-19 09:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260219_0008"
down_revision = "20260218_0007"
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    try:
        return {str(col.get("name") or "").strip() for col in inspector.get_columns(table_name)}
    except Exception:
        return set()


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    try:
        return {str(idx.get("name") or "").strip() for idx in inspector.get_indexes(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = _column_names(inspector, "item_attachments")
    if "scope_code" not in columns:
        op.add_column(
            "item_attachments",
            sa.Column("scope_code", sa.String(length=16), nullable=False, server_default="GENERAL"),
        )
    if "slot_code" not in columns:
        op.add_column(
            "item_attachments",
            sa.Column("slot_code", sa.String(length=64), nullable=True),
        )
    if "note" not in columns:
        op.add_column(
            "item_attachments",
            sa.Column("note", sa.Text(), nullable=True),
        )

    op.execute("UPDATE item_attachments SET scope_code='GENERAL' WHERE scope_code IS NULL")

    indexes = _index_names(inspector, "item_attachments")
    if "ix_item_attachments_scope_code" not in indexes:
        op.create_index(
            "ix_item_attachments_scope_code",
            "item_attachments",
            ["scope_code"],
            unique=False,
        )
    if "ix_item_attachments_slot_code" not in indexes:
        op.create_index(
            "ix_item_attachments_slot_code",
            "item_attachments",
            ["slot_code"],
            unique=False,
        )
    if "ix_item_attachments_item_scope_uploaded_at" not in indexes:
        op.create_index(
            "ix_item_attachments_item_scope_uploaded_at",
            "item_attachments",
            ["item_id", "scope_code", "uploaded_at"],
            unique=False,
        )
    if "ix_item_attachments_item_slot_uploaded_at" not in indexes:
        op.create_index(
            "ix_item_attachments_item_slot_uploaded_at",
            "item_attachments",
            ["item_id", "slot_code", "uploaded_at"],
            unique=False,
        )

    op.alter_column("item_attachments", "scope_code", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = _index_names(inspector, "item_attachments")

    if "ix_item_attachments_item_slot_uploaded_at" in indexes:
        op.drop_index("ix_item_attachments_item_slot_uploaded_at", table_name="item_attachments")
    if "ix_item_attachments_item_scope_uploaded_at" in indexes:
        op.drop_index("ix_item_attachments_item_scope_uploaded_at", table_name="item_attachments")
    if "ix_item_attachments_slot_code" in indexes:
        op.drop_index("ix_item_attachments_slot_code", table_name="item_attachments")
    if "ix_item_attachments_scope_code" in indexes:
        op.drop_index("ix_item_attachments_scope_code", table_name="item_attachments")

    columns = _column_names(inspector, "item_attachments")
    if "note" in columns:
        op.drop_column("item_attachments", "note")
    if "slot_code" in columns:
        op.drop_column("item_attachments", "slot_code")
    if "scope_code" in columns:
        op.drop_column("item_attachments", "scope_code")

