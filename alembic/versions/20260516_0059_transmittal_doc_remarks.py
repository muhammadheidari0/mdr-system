"""Add row remarks to transmittal documents.

Revision ID: 20260516_0059
Revises: 20260516_0058
Create Date: 2026-05-16 11:40:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260516_0059"
down_revision = "20260516_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transmittal_docs", sa.Column("remarks", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("transmittal_docs", "remarks")
