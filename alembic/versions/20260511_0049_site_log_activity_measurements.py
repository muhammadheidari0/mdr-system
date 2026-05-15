"""Add consultant measurement and QC fields to site log activities.

Revision ID: 20260511_0049
Revises: 20260510_0048
Create Date: 2026-05-11 10:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260511_0049"
down_revision = "20260510_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_log_activity_rows", sa.Column("supervisor_today_quantity", sa.Float(), nullable=True))
    op.add_column("site_log_activity_rows", sa.Column("supervisor_cumulative_quantity", sa.Float(), nullable=True))
    op.add_column("site_log_activity_rows", sa.Column("supervisor_unit", sa.String(length=64), nullable=True))
    op.add_column(
        "site_log_activity_rows",
        sa.Column("qc_status", sa.String(length=32), nullable=True, server_default="PENDING"),
    )
    op.add_column("site_log_activity_rows", sa.Column("qc_at", sa.DateTime(), nullable=True))
    op.add_column("site_log_activity_rows", sa.Column("qc_by_user_id", sa.Integer(), nullable=True))
    op.add_column("site_log_activity_rows", sa.Column("qc_note", sa.Text(), nullable=True))
    op.add_column(
        "site_log_activity_rows",
        sa.Column("measurement_status", sa.String(length=32), nullable=True, server_default="DRAFT"),
    )
    op.add_column("site_log_activity_rows", sa.Column("measurement_updated_at", sa.DateTime(), nullable=True))
    op.add_column("site_log_activity_rows", sa.Column("measurement_updated_by_user_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_site_log_activity_rows_qc_by_user",
        "site_log_activity_rows",
        "users",
        ["qc_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_site_log_activity_rows_measurement_updated_by_user",
        "site_log_activity_rows",
        "users",
        ["measurement_updated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_site_log_activity_rows_qc_by_user_id",
        "site_log_activity_rows",
        ["qc_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_site_log_activity_rows_measurement_updated_by_user_id",
        "site_log_activity_rows",
        ["measurement_updated_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_site_log_activity_rows_measurement_qc",
        "site_log_activity_rows",
        ["measurement_status", "qc_status"],
        unique=False,
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE site_log_activity_rows
            SET
                qc_status = COALESCE(qc_status, 'PENDING'),
                measurement_status = COALESCE(measurement_status, 'DRAFT')
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_site_log_activity_rows_measurement_qc", table_name="site_log_activity_rows")
    op.drop_index("ix_site_log_activity_rows_measurement_updated_by_user_id", table_name="site_log_activity_rows")
    op.drop_index("ix_site_log_activity_rows_qc_by_user_id", table_name="site_log_activity_rows")
    op.drop_constraint(
        "fk_site_log_activity_rows_measurement_updated_by_user",
        "site_log_activity_rows",
        type_="foreignkey",
    )
    op.drop_constraint("fk_site_log_activity_rows_qc_by_user", "site_log_activity_rows", type_="foreignkey")
    op.drop_column("site_log_activity_rows", "measurement_updated_by_user_id")
    op.drop_column("site_log_activity_rows", "measurement_updated_at")
    op.drop_column("site_log_activity_rows", "measurement_status")
    op.drop_column("site_log_activity_rows", "qc_note")
    op.drop_column("site_log_activity_rows", "qc_by_user_id")
    op.drop_column("site_log_activity_rows", "qc_at")
    op.drop_column("site_log_activity_rows", "qc_status")
    op.drop_column("site_log_activity_rows", "supervisor_unit")
    op.drop_column("site_log_activity_rows", "supervisor_cumulative_quantity")
    op.drop_column("site_log_activity_rows", "supervisor_today_quantity")
