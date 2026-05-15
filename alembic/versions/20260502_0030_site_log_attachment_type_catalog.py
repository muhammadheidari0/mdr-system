"""Add site log attachment type catalog.

Revision ID: 20260502_0030
Revises: 20260501_0029
Create Date: 2026-05-02 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260502_0030"
down_revision = "20260501_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_log_attachment_type_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_site_log_attachment_type_catalog_code"),
    )
    op.create_index("ix_site_log_attachment_type_catalog_code", "site_log_attachment_type_catalog", ["code"])

    attachment_type_table = sa.table(
        "site_log_attachment_type_catalog",
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        attachment_type_table,
        [
            {"code": "PHOTO", "label": "عکس", "sort_order": 10, "is_active": True},
            {"code": "IR", "label": "فرم بازرسی", "sort_order": 20, "is_active": True},
            {"code": "QC", "label": "مدرک QC", "sort_order": 30, "is_active": True},
            {"code": "TEST", "label": "نتیجه تست", "sort_order": 40, "is_active": True},
            {"code": "SKETCH", "label": "کروکی / اسکچ", "sort_order": 50, "is_active": True},
            {"code": "REPORT", "label": "گزارش", "sort_order": 60, "is_active": True},
            {"code": "OTHER", "label": "سایر", "sort_order": 90, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_site_log_attachment_type_catalog_code", "site_log_attachment_type_catalog")
    op.drop_table("site_log_attachment_type_catalog")
