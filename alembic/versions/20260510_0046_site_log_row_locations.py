"""Add site log equipment and material row locations.

Revision ID: 20260510_0046
Revises: 20260508_0045
Create Date: 2026-05-10 09:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260510_0046"
down_revision = "20260508_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_log_equipment_rows", sa.Column("work_location", sa.String(length=255), nullable=True))
    op.add_column("site_log_material_rows", sa.Column("consumption_location", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("site_log_material_rows", "consumption_location")
    op.drop_column("site_log_equipment_rows", "work_location")
