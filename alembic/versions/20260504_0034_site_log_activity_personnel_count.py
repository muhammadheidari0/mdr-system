"""Add personnel count to site log activity rows.

Revision ID: 20260504_0034
Revises: 20260504_0033
Create Date: 2026-05-04 09:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260504_0034"
down_revision = "20260504_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("site_log_activity_rows") as batch_op:
        batch_op.add_column(sa.Column("personnel_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("site_log_activity_rows") as batch_op:
        batch_op.drop_column("personnel_count")
