"""Clean slate: remove TECH report subtype records and related comm items.

Revision ID: 20260220_0010
Revises: 20260219_0009
Create Date: 2026-02-20 10:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260220_0010"
down_revision = "20260219_0009"
branch_labels = None
depends_on = None


REPORT_SUBTYPES = (
    "DAILY_REPORT",
    "WEEKLY_REPORT",
    "MANPOWER_REPORT",
    "EQUIPMENT_REPORT",
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM comm_items
            WHERE item_type = 'TECH'
              AND id IN (
                SELECT td.comm_item_id
                FROM tech_details td
                WHERE td.tech_subtype_code IN (
                  'DAILY_REPORT',
                  'WEEKLY_REPORT',
                  'MANPOWER_REPORT',
                  'EQUIPMENT_REPORT'
                )
              )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM tech_subtypes
            WHERE code IN (
              'DAILY_REPORT',
              'WEEKLY_REPORT',
              'MANPOWER_REPORT',
              'EQUIPMENT_REPORT'
            )
            """
        )
    )


def downgrade() -> None:
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
