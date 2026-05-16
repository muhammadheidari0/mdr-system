"""Add selected file kind to transmittal documents.

Revision ID: 20260516_0058
Revises: 20260515_0057
Create Date: 2026-05-16 10:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260516_0058"
down_revision = "20260515_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transmittal_docs",
        sa.Column("file_kind", sa.String(length=20), nullable=False, server_default="pdf"),
    )


def downgrade() -> None:
    op.drop_column("transmittal_docs", "file_kind")
