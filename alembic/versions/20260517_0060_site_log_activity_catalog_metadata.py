"""Add metadata fields to site log activity catalog.

Revision ID: 20260517_0060
Revises: 20260516_0059
Create Date: 2026-05-17 03:15:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260517_0060"
down_revision = "20260516_0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("site_log_activity_catalog") as batch_op:
        batch_op.add_column(sa.Column("activity_type", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("activity_type_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("floor", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("wbs_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("default_quantity", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("site_log_activity_catalog") as batch_op:
        batch_op.drop_column("default_quantity")
        batch_op.drop_column("wbs_code")
        batch_op.drop_column("floor")
        batch_op.drop_column("activity_type_code")
        batch_op.drop_column("activity_type")
