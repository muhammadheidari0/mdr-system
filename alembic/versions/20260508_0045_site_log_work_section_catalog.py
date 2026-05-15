"""Add site log manpower work section catalog.

Revision ID: 20260508_0045
Revises: 20260507_0044
Create Date: 2026-05-08 10:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260508_0045"
down_revision = "20260507_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_log_work_section_catalog",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("code", name="uq_site_log_work_section_catalog_code"),
    )
    op.create_index("ix_site_log_work_section_catalog_code", "site_log_work_section_catalog", ["code"])
    op.add_column("site_log_manpower_rows", sa.Column("work_section_label", sa.String(length=255), nullable=True))
    op.bulk_insert(
        sa.table(
            "site_log_work_section_catalog",
            sa.column("code", sa.String()),
            sa.column("label", sa.String()),
            sa.column("sort_order", sa.Integer()),
            sa.column("is_active", sa.Boolean()),
        ),
        [
            {"code": "TECH_OFFICE", "label": "دفتر فنی", "sort_order": 10, "is_active": True},
            {"code": "EXECUTION", "label": "اجرا / عملیات", "sort_order": 20, "is_active": True},
            {"code": "LOGISTICS", "label": "انبار و لجستیک", "sort_order": 30, "is_active": True},
            {"code": "QC_HSE", "label": "کنترل کیفیت / HSE", "sort_order": 40, "is_active": True},
            {"code": "ADMIN_SUPPORT", "label": "اداری و پشتیبانی", "sort_order": 50, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_column("site_log_manpower_rows", "work_section_label")
    op.drop_index("ix_site_log_work_section_catalog_code", table_name="site_log_work_section_catalog")
    op.drop_table("site_log_work_section_catalog")
