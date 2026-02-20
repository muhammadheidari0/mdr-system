"""Add generic mirror provider fields for storage backends.

Revision ID: 20260221_0014
Revises: 20260221_0013
Create Date: 2026-02-21 19:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260221_0014"
down_revision = "20260221_0013"
branch_labels = None
depends_on = None


TABLES = (
    "archive_files",
    "correspondence_attachments",
    "item_attachments",
)


def _index_name(table: str, suffix: str) -> str:
    safe = table.replace("-", "_")
    return f"ix_{safe}_{suffix}"


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("mirror_provider", sa.String(length=32), nullable=True))
        op.add_column(table, sa.Column("mirror_remote_id", sa.String(length=255), nullable=True))
        op.add_column(table, sa.Column("mirror_remote_url", sa.String(length=1024), nullable=True))
        op.create_index(
            _index_name(table, "mirror_provider"),
            table,
            ["mirror_provider"],
            unique=False,
        )
        op.create_index(
            _index_name(table, "mirror_remote_id"),
            table,
            ["mirror_remote_id"],
            unique=False,
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(_index_name(table, "mirror_remote_id"), table_name=table)
        op.drop_index(_index_name(table, "mirror_provider"), table_name=table)
        op.drop_column(table, "mirror_remote_url")
        op.drop_column(table, "mirror_remote_id")
        op.drop_column(table, "mirror_provider")
