"""Add site log material catalog.

Revision ID: 20260510_0047
Revises: 20260510_0046
Create Date: 2026-05-10 10:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260510_0047"
down_revision = "20260510_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_log_material_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_site_log_material_catalog_code"),
    )
    op.create_index(op.f("ix_site_log_material_catalog_code"), "site_log_material_catalog", ["code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_site_log_material_catalog_code"), table_name="site_log_material_catalog")
    op.drop_table("site_log_material_catalog")
