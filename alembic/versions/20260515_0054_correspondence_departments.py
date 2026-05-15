"""Add correspondence departments.

Revision ID: 20260515_0054
Revises: 20260513_0053
Create Date: 2026-05-15 10:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260515_0054"
down_revision = "20260513_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "correspondence_departments",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name_e", sa.String(length=255), nullable=False),
        sa.Column("name_p", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_correspondence_departments")),
    )
    op.create_index(
        "ix_correspondence_departments_active_sort",
        "correspondence_departments",
        ["is_active", "sort_order", "code"],
        unique=False,
    )

    with op.batch_alter_table("correspondences") as batch_op:
        batch_op.add_column(sa.Column("department_code", sa.String(length=32), nullable=True))
        batch_op.create_foreign_key(
            "fk_correspondences_department_code_correspondence_departments",
            "correspondence_departments",
            ["department_code"],
            ["code"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_correspondences_department_code", ["department_code"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("correspondences") as batch_op:
        batch_op.drop_index("ix_correspondences_department_code")
        batch_op.drop_constraint(
            "fk_correspondences_department_code_correspondence_departments",
            type_="foreignkey",
        )
        batch_op.drop_column("department_code")

    op.drop_index("ix_correspondence_departments_active_sort", table_name="correspondence_departments")
    op.drop_table("correspondence_departments")
