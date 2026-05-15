"""Add returned workflow status for site logs.

Revision ID: 20260511_0050
Revises: 20260511_0049
Create Date: 2026-05-11 12:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260511_0050"
down_revision = "20260511_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO site_log_workflow_statuses (code, label, sort_order, is_active)
            SELECT 'RETURNED', 'Returned', 25, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM site_log_workflow_statuses WHERE code = 'RETURNED'
            )
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM site_log_workflow_statuses WHERE code = 'RETURNED'"))
