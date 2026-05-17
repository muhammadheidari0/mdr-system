"""Add location and floor fields to site log rows.

Revision ID: 20260517_0061
Revises: 20260517_0060
Create Date: 2026-05-17 03:35:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260517_0061"
down_revision = "20260517_0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("site_log_manpower_rows") as batch_op:
        batch_op.add_column(sa.Column("work_location", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("work_floor", sa.String(length=64), nullable=True))

    with op.batch_alter_table("site_log_equipment_rows") as batch_op:
        batch_op.add_column(sa.Column("work_floor", sa.String(length=64), nullable=True))

    with op.batch_alter_table("site_log_activity_rows") as batch_op:
        batch_op.add_column(sa.Column("floor", sa.String(length=64), nullable=True))

    with op.batch_alter_table("site_log_material_rows") as batch_op:
        batch_op.add_column(sa.Column("consumption_floor", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("site_log_material_rows") as batch_op:
        batch_op.drop_column("consumption_floor")

    with op.batch_alter_table("site_log_activity_rows") as batch_op:
        batch_op.drop_column("floor")

    with op.batch_alter_table("site_log_equipment_rows") as batch_op:
        batch_op.drop_column("work_floor")

    with op.batch_alter_table("site_log_manpower_rows") as batch_op:
        batch_op.drop_column("work_floor")
        batch_op.drop_column("work_location")
