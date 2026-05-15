"""Seed sample PMS templates for site-log activities.

Revision ID: 20260505_0037
Revises: 20260505_0036
Create Date: 2026-05-05 11:20:00
"""
from __future__ import annotations

from alembic import op


revision = "20260505_0037"
down_revision = "20260505_0036"
branch_labels = None
depends_on = None


TEMPLATES = (
    (
        "PMS-STUD",
        "Stud installation",
        10,
        (
            ("INSTALL", "Install studs", 80, 10),
            ("QC", "QC check", 20, 20),
        ),
    ),
    (
        "PMS-CONCRETE",
        "Concrete work",
        20,
        (
            ("PREP", "Preparation", 20, 10),
            ("POUR", "Pouring", 60, 20),
            ("QC", "Curing and QC", 20, 30),
        ),
    ),
    (
        "PMS-EQUIP",
        "Equipment installation",
        30,
        (
            ("DELIVERY", "Delivery", 20, 10),
            ("INSTALL", "Installation", 60, 20),
            ("TEST", "Testing", 20, 30),
        ),
    ),
)


def upgrade() -> None:
    for code, title, sort_order, steps in TEMPLATES:
        op.execute(
            f"""
            INSERT INTO site_log_pms_templates
                (code, title, description, version, sort_order, is_active, created_at, updated_at)
            VALUES
                ('{code}', '{title}', 'Default sample template', 1, {sort_order}, true, now(), now())
            ON CONFLICT (code) DO NOTHING
            """
        )
        for step_code, step_title, weight, step_sort in steps:
            op.execute(
                f"""
                INSERT INTO site_log_pms_template_steps
                    (template_id, step_code, step_title, weight_pct, sort_order, is_active)
                SELECT id, '{step_code}', '{step_title}', {weight}, {step_sort}, true
                FROM site_log_pms_templates
                WHERE code = '{code}'
                ON CONFLICT (template_id, step_code) DO NOTHING
                """
            )


def downgrade() -> None:
    codes = ", ".join(f"'{code}'" for code, _title, _sort, _steps in TEMPLATES)
    op.execute(
        f"""
        DELETE FROM site_log_activity_pms_mappings
        WHERE template_id IN (SELECT id FROM site_log_pms_templates WHERE code IN ({codes}))
        """
    )
    op.execute(
        f"""
        DELETE FROM site_log_pms_template_steps
        WHERE template_id IN (SELECT id FROM site_log_pms_templates WHERE code IN ({codes}))
        """
    )
    op.execute(f"DELETE FROM site_log_pms_templates WHERE code IN ({codes})")
