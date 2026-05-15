"""Extend site logs for workshop report form updates.

Revision ID: 20260501_0027
Revises: 20260501_0026
Create Date: 2026-05-01 12:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260501_0027"
down_revision = "20260501_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("site_logs") as batch_op:
        batch_op.alter_column(
            "discipline_code",
            existing_type=sa.String(length=20),
            nullable=True,
        )
        batch_op.add_column(sa.Column("shift", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("contract_number", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("current_work_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("next_plan_summary", sa.Text(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE site_logs
            SET current_work_summary = summary
            WHERE current_work_summary IS NULL
              AND summary IS NOT NULL
              AND TRIM(summary) <> ''
            """
        )
    )

    with op.batch_alter_table("site_log_activity_rows") as batch_op:
        batch_op.add_column(sa.Column("location", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("unit", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("today_quantity", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("cumulative_quantity", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("activity_status", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("stop_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("site_log_activity_rows") as batch_op:
        batch_op.drop_column("stop_reason")
        batch_op.drop_column("activity_status")
        batch_op.drop_column("cumulative_quantity")
        batch_op.drop_column("today_quantity")
        batch_op.drop_column("unit")
        batch_op.drop_column("location")

    with op.batch_alter_table("site_logs") as batch_op:
        batch_op.drop_column("next_plan_summary")
        batch_op.drop_column("current_work_summary")
        batch_op.drop_column("contract_number")
        batch_op.drop_column("shift")
        batch_op.alter_column(
            "discipline_code",
            existing_type=sa.String(length=20),
            nullable=False,
        )
