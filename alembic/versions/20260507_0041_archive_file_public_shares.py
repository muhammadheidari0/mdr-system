"""archive file public shares

Revision ID: 20260507_0041
Revises: 20260506_0040
Create Date: 2026-05-07 03:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260507_0041"
down_revision = "20260506_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "archive_file_public_shares",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="nextcloud"),
        sa.Column("provider_share_id", sa.String(length=128), nullable=False),
        sa.Column("token", sa.String(length=128), nullable=True),
        sa.Column("share_url", sa.String(length=1024), nullable=False),
        sa.Column("resolved_path", sa.String(length=1024), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("permissions", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("password_set", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("revoked_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["archive_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_archive_file_public_shares_file",
        "archive_file_public_shares",
        ["file_id"],
    )
    op.create_index(
        "ix_archive_file_public_shares_provider_share",
        "archive_file_public_shares",
        ["provider", "provider_share_id"],
    )
    op.create_index(
        "ix_archive_file_public_shares_active",
        "archive_file_public_shares",
        ["file_id", "revoked_at", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_archive_file_public_shares_active", table_name="archive_file_public_shares")
    op.drop_index("ix_archive_file_public_shares_provider_share", table_name="archive_file_public_shares")
    op.drop_index("ix_archive_file_public_shares_file", table_name="archive_file_public_shares")
    op.drop_table("archive_file_public_shares")
