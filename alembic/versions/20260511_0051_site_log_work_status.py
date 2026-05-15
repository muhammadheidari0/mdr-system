"""Add site work status to site logs.

Revision ID: 20260511_0051
Revises: 20260511_0050
Create Date: 2026-05-11 14:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260511_0051"
down_revision = "20260511_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_logs",
        sa.Column("work_status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
    )
    op.create_index("ix_site_logs_work_status", "site_logs", ["work_status"], unique=False)
    op.execute("UPDATE site_logs SET work_status = 'ACTIVE' WHERE work_status IS NULL OR work_status = ''")


def downgrade() -> None:
    op.drop_index("ix_site_logs_work_status", table_name="site_logs")
    op.drop_column("site_logs", "work_status")
