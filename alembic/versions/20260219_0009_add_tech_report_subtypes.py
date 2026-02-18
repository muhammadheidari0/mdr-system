"""Seed additional TECH report subtypes.

Revision ID: 20260219_0009
Revises: 20260219_0008
Create Date: 2026-02-19 09:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260219_0009"
down_revision = "20260219_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = [
        ("DAILY_REPORT", "Daily Report", 50),
        ("WEEKLY_REPORT", "Weekly Report", 55),
        ("MANPOWER_REPORT", "Manpower Report", 58),
        ("EQUIPMENT_REPORT", "Equipment Report", 59),
    ]
    for code, label, sort_order in rows:
        exists = bind.execute(
            sa.text("SELECT 1 FROM tech_subtypes WHERE code = :code LIMIT 1"),
            {"code": code},
        ).first()
        if exists:
            bind.execute(
                sa.text(
                    """
                    UPDATE tech_subtypes
                    SET label = :label,
                        sort_order = :sort_order,
                        is_active = TRUE
                    WHERE code = :code
                    """
                ),
                {"code": code, "label": label, "sort_order": int(sort_order)},
            )
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO tech_subtypes (code, label, sort_order, is_active)
                VALUES (:code, :label, :sort_order, TRUE)
                """
            ),
            {"code": code, "label": label, "sort_order": int(sort_order)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM tech_subtypes
            WHERE code IN ('WEEKLY_REPORT', 'MANPOWER_REPORT', 'EQUIPMENT_REPORT')
            """
        )
    )

