"""Add contract snapshot fields to site logs.

Revision ID: 20260501_0028
Revises: 20260501_0027
Create Date: 2026-05-01 13:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260501_0028"
down_revision = "20260501_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("site_logs") as batch_op:
        batch_op.add_column(sa.Column("contract_subject", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("contract_block", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("site_logs") as batch_op:
        batch_op.drop_column("contract_block")
        batch_op.drop_column("contract_subject")
