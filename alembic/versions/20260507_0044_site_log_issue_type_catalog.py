"""Add site log issue type catalog.

Revision ID: 20260507_0044
Revises: 20260507_0043
Create Date: 2026-05-07 08:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260507_0044"
down_revision = "20260507_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_log_issue_type_catalog",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("code", name="uq_site_log_issue_type_catalog_code"),
    )
    op.create_index("ix_site_log_issue_type_catalog_code", "site_log_issue_type_catalog", ["code"])
    op.bulk_insert(
        sa.table(
            "site_log_issue_type_catalog",
            sa.column("code", sa.String()),
            sa.column("label", sa.String()),
            sa.column("sort_order", sa.Integer()),
            sa.column("is_active", sa.Boolean()),
        ),
        [
            {"code": "MATERIAL", "label": "کمبود مصالح", "sort_order": 10, "is_active": True},
            {"code": "ACCESS", "label": "محدودیت دسترسی", "sort_order": 20, "is_active": True},
            {"code": "EQUIPMENT", "label": "مشکل تجهیزات", "sort_order": 30, "is_active": True},
            {"code": "MANPOWER", "label": "کمبود نیروی انسانی", "sort_order": 40, "is_active": True},
            {"code": "PERMIT", "label": "مجوز یا هماهنگی", "sort_order": 50, "is_active": True},
            {"code": "DESIGN", "label": "ابهام فنی یا نقشه", "sort_order": 60, "is_active": True},
            {"code": "SAFETY", "label": "ایمنی", "sort_order": 70, "is_active": True},
            {"code": "WEATHER", "label": "شرایط جوی", "sort_order": 80, "is_active": True},
            {"code": "OTHER", "label": "سایر", "sort_order": 90, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_site_log_issue_type_catalog_code", table_name="site_log_issue_type_catalog")
    op.drop_table("site_log_issue_type_catalog")
