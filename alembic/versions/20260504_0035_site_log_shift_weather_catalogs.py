"""Add site log shift and weather catalogs.

Revision ID: 20260504_0035
Revises: 20260504_0034
Create Date: 2026-05-04 18:55:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260504_0035"
down_revision = "20260504_0034"
branch_labels = None
depends_on = None


def _create_catalog_table(table_name: str, unique_name: str) -> None:
    op.create_table(
        table_name,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("code", name=unique_name),
    )
    op.create_index(f"ix_{table_name}_code", table_name, ["code"])


def upgrade() -> None:
    _create_catalog_table("site_log_shift_catalog", "uq_site_log_shift_catalog_code")
    _create_catalog_table("site_log_weather_catalog", "uq_site_log_weather_catalog_code")

    op.bulk_insert(
        sa.table(
            "site_log_shift_catalog",
            sa.column("code", sa.String()),
            sa.column("label", sa.String()),
            sa.column("sort_order", sa.Integer()),
            sa.column("is_active", sa.Boolean()),
        ),
        [
            {"code": "DAY", "label": "روز", "sort_order": 10, "is_active": True},
            {"code": "NIGHT", "label": "شب", "sort_order": 20, "is_active": True},
        ],
    )
    op.bulk_insert(
        sa.table(
            "site_log_weather_catalog",
            sa.column("code", sa.String()),
            sa.column("label", sa.String()),
            sa.column("sort_order", sa.Integer()),
            sa.column("is_active", sa.Boolean()),
        ),
        [
            {"code": "CLEAR", "label": "صاف", "sort_order": 10, "is_active": True},
            {"code": "CLOUDY", "label": "ابری", "sort_order": 20, "is_active": True},
            {"code": "RAIN", "label": "بارانی", "sort_order": 30, "is_active": True},
            {"code": "WINDY", "label": "باد", "sort_order": 40, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_site_log_weather_catalog_code", table_name="site_log_weather_catalog")
    op.drop_table("site_log_weather_catalog")
    op.drop_index("ix_site_log_shift_catalog_code", table_name="site_log_shift_catalog")
    op.drop_table("site_log_shift_catalog")
