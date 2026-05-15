"""Add equipment counts to site log rows.

Revision ID: 20260507_0043
Revises: 20260507_0042
Create Date: 2026-05-07 07:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260507_0043"
down_revision = "20260507_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_log_equipment_rows", sa.Column("claimed_count", sa.Integer(), nullable=True))
    op.add_column("site_log_equipment_rows", sa.Column("verified_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("site_log_equipment_rows", "verified_count")
    op.drop_column("site_log_equipment_rows", "claimed_count")
