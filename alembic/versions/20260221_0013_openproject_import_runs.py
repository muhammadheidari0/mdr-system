"""Add OpenProject import run and row log tables.

Revision ID: 20260221_0013
Revises: 20260220_0012
Create Date: 2026-02-21 09:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260221_0013"
down_revision = "20260220_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "openproject_import_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_no", sa.String(length=128), nullable=False),
        sa.Column("status_code", sa.String(length=32), nullable=False, server_default="VALIDATED"),
        sa.Column("source_file_name", sa.String(length=255), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("target_parent_work_package_id", sa.Integer(), nullable=True),
        sa.Column("started_by_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["started_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_no", name="uq_openproject_import_runs_run_no"),
    )
    op.create_index("ix_openproject_import_runs_run_no", "openproject_import_runs", ["run_no"], unique=False)
    op.create_index(
        "ix_openproject_import_runs_status_created",
        "openproject_import_runs",
        ["status_code", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_openproject_import_runs_source_sha256",
        "openproject_import_runs",
        ["source_sha256"],
        unique=False,
    )
    op.create_index(
        "ix_openproject_import_runs_started_by_id",
        "openproject_import_runs",
        ["started_by_id"],
        unique=False,
    )

    op.create_table(
        "openproject_import_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("task_name", sa.String(length=255), nullable=True),
        sa.Column("duration_raw", sa.String(length=128), nullable=True),
        sa.Column("start_raw", sa.String(length=128), nullable=True),
        sa.Column("finish_raw", sa.String(length=128), nullable=True),
        sa.Column("predecessors_raw", sa.String(length=255), nullable=True),
        sa.Column("resource_names_raw", sa.String(length=255), nullable=True),
        sa.Column("normalized_start_date", sa.String(length=10), nullable=True),
        sa.Column("normalized_finish_date", sa.String(length=10), nullable=True),
        sa.Column("validation_status", sa.String(length=16), nullable=False, server_default="INVALID"),
        sa.Column("execution_status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("created_work_package_id", sa.Integer(), nullable=True),
        sa.Column("openproject_href", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["openproject_import_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "row_no", name="uq_openproject_import_rows_run_row"),
    )
    op.create_index("ix_openproject_import_rows_run_id", "openproject_import_rows", ["run_id"], unique=False)
    op.create_index(
        "ix_openproject_import_rows_run_row",
        "openproject_import_rows",
        ["run_id", "row_no"],
        unique=False,
    )
    op.create_index(
        "ix_openproject_import_rows_validation_status",
        "openproject_import_rows",
        ["validation_status"],
        unique=False,
    )
    op.create_index(
        "ix_openproject_import_rows_execution_status",
        "openproject_import_rows",
        ["execution_status"],
        unique=False,
    )
    op.create_index(
        "ix_openproject_import_rows_run_exec",
        "openproject_import_rows",
        ["run_id", "execution_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("openproject_import_rows")
    op.drop_table("openproject_import_runs")
