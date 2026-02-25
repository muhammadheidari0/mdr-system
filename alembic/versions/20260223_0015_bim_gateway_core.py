"""Create BIM gateway core tables for Revit publish/schedule/writeback.

Revision ID: 20260223_0015
Revises: 20260221_0014
Create Date: 2026-02-23 07:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260223_0015"
down_revision = "20260221_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bim_publish_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_uid", sa.String(length=64), nullable=False),
        sa.Column("run_client_id", sa.String(length=128), nullable=True),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("model_guid", sa.String(length=64), nullable=True),
        sa.Column("model_title", sa.String(length=255), nullable=True),
        sa.Column("revit_version", sa.String(length=16), nullable=True),
        sa.Column("plugin_version", sa.String(length=32), nullable=True),
        sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_uid", name="uq_bim_publish_runs_run_uid"),
    )
    op.create_index("ix_bim_publish_runs_run_uid", "bim_publish_runs", ["run_uid"], unique=True)
    op.create_index(
        "ix_bim_publish_runs_project_status",
        "bim_publish_runs",
        ["project_code", "status"],
        unique=False,
    )
    op.create_index(
        "ix_bim_publish_runs_run_client_id",
        "bim_publish_runs",
        ["run_client_id"],
        unique=False,
    )
    op.create_index("ix_bim_publish_runs_model_guid", "bim_publish_runs", ["model_guid"], unique=False)
    op.create_index("ix_bim_publish_runs_status", "bim_publish_runs", ["status"], unique=False)

    op.create_table(
        "bim_publish_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("sheet_unique_id", sa.String(length=128), nullable=False),
        sa.Column("sheet_number", sa.String(length=64), nullable=True),
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
        sa.Column("doc_number", sa.String(length=255), nullable=True),
        sa.Column("requested_revision", sa.String(length=32), nullable=False),
        sa.Column("status_code", sa.String(length=32), nullable=True),
        sa.Column("include_native", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("idempotency_hash", sa.String(length=128), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("applied_revision", sa.String(length=32), nullable=True),
        sa.Column("pdf_file_id", sa.Integer(), nullable=True),
        sa.Column("native_file_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["mdr_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["native_file_id"], ["archive_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pdf_file_id"], ["archive_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["bim_publish_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_hash", name="uq_bim_publish_items_idempotency_hash"),
        sa.UniqueConstraint("run_id", "item_index", name="uq_bim_publish_items_run_item_index"),
    )
    op.create_index("ix_bim_publish_items_run_id", "bim_publish_items", ["run_id"], unique=False)
    op.create_index("ix_bim_publish_items_project_code", "bim_publish_items", ["project_code"], unique=False)
    op.create_index(
        "ix_bim_publish_items_sheet_unique_id",
        "bim_publish_items",
        ["sheet_unique_id"],
        unique=False,
    )
    op.create_index("ix_bim_publish_items_doc_number", "bim_publish_items", ["doc_number"], unique=False)
    op.create_index(
        "ix_bim_publish_items_idempotency_hash",
        "bim_publish_items",
        ["idempotency_hash"],
        unique=True,
    )
    op.create_index(
        "ix_bim_publish_items_project_sheet_revision",
        "bim_publish_items",
        ["project_code", "sheet_unique_id", "requested_revision"],
        unique=False,
    )
    op.create_index(
        "ix_bim_publish_items_run_state",
        "bim_publish_items",
        ["run_id", "state"],
        unique=False,
    )
    op.create_index("ix_bim_publish_items_file_sha256", "bim_publish_items", ["file_sha256"], unique=False)

    op.create_table(
        "bim_schedule_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_uid", sa.String(length=64), nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("profile_code", sa.String(length=32), nullable=False),
        sa.Column("model_guid", sa.String(length=64), nullable=False),
        sa.Column("view_name", sa.String(length=255), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="staging"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_by_id", sa.Integer(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rejected_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_uid", name="uq_bim_schedule_runs_run_uid"),
    )
    op.create_index("ix_bim_schedule_runs_run_uid", "bim_schedule_runs", ["run_uid"], unique=True)
    op.create_index("ix_bim_schedule_runs_project_code", "bim_schedule_runs", ["project_code"], unique=False)
    op.create_index("ix_bim_schedule_runs_profile_code", "bim_schedule_runs", ["profile_code"], unique=False)
    op.create_index("ix_bim_schedule_runs_model_guid", "bim_schedule_runs", ["model_guid"], unique=False)
    op.create_index("ix_bim_schedule_runs_status", "bim_schedule_runs", ["status"], unique=False)
    op.create_index(
        "ix_bim_schedule_runs_project_profile_status",
        "bim_schedule_runs",
        ["project_code", "profile_code", "status"],
        unique=False,
    )

    op.create_table(
        "bim_schedule_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("row_state", sa.String(length=16), nullable=False, server_default="VALID"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("element_key", sa.String(length=255), nullable=True),
        sa.Column("equipment_key", sa.String(length=255), nullable=True),
        sa.Column("values_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["bim_schedule_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "row_no", name="uq_bim_schedule_rows_run_row_no"),
    )
    op.create_index("ix_bim_schedule_rows_run_id", "bim_schedule_rows", ["run_id"], unique=False)
    op.create_index(
        "ix_bim_schedule_rows_run_state",
        "bim_schedule_rows",
        ["run_id", "row_state"],
        unique=False,
    )
    op.create_index("ix_bim_schedule_rows_element_key", "bim_schedule_rows", ["element_key"], unique=False)
    op.create_index("ix_bim_schedule_rows_equipment_key", "bim_schedule_rows", ["equipment_key"], unique=False)

    op.create_table(
        "bim_mto_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("model_guid", sa.String(length=64), nullable=False),
        sa.Column("element_key", sa.String(length=255), nullable=False),
        sa.Column("values_json", sa.Text(), nullable=True),
        sa.Column("source_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_run_id"], ["bim_schedule_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bim_mto_items_project_model_element",
        "bim_mto_items",
        ["project_code", "model_guid", "element_key"],
        unique=True,
    )
    op.create_index("ix_bim_mto_items_source_run_id", "bim_mto_items", ["source_run_id"], unique=False)

    op.create_table(
        "bim_equipment_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("model_guid", sa.String(length=64), nullable=False),
        sa.Column("equipment_key", sa.String(length=255), nullable=False),
        sa.Column("values_json", sa.Text(), nullable=True),
        sa.Column("source_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_run_id"], ["bim_schedule_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bim_equipment_items_project_model_equipment",
        "bim_equipment_items",
        ["project_code", "model_guid", "equipment_key"],
        unique=True,
    )
    op.create_index(
        "ix_bim_equipment_items_source_run_id",
        "bim_equipment_items",
        ["source_run_id"],
        unique=False,
    )

    op.create_table(
        "bim_revit_sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_uid", sa.String(length=64), nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("client_model_guid", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("requested_by_id", sa.Integer(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("applied_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_uid", name="uq_bim_revit_sync_runs_run_uid"),
    )
    op.create_index("ix_bim_revit_sync_runs_run_uid", "bim_revit_sync_runs", ["run_uid"], unique=True)
    op.create_index("ix_bim_revit_sync_runs_project_code", "bim_revit_sync_runs", ["project_code"], unique=False)
    op.create_index(
        "ix_bim_revit_sync_runs_client_model_guid",
        "bim_revit_sync_runs",
        ["client_model_guid"],
        unique=False,
    )
    op.create_index("ix_bim_revit_sync_runs_status", "bim_revit_sync_runs", ["status"], unique=False)
    op.create_index(
        "ix_bim_revit_sync_runs_project_model_status",
        "bim_revit_sync_runs",
        ["project_code", "client_model_guid", "status"],
        unique=False,
    )

    op.create_table(
        "bim_revit_sync_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("sync_key", sa.String(length=255), nullable=False),
        sa.Column("source_log_id", sa.Integer(), nullable=False),
        sa.Column("section_code", sa.String(length=32), nullable=False),
        sa.Column("row_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False, server_default="upsert"),
        sa.Column("row_hash", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["bim_revit_sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sync_key", name="uq_bim_revit_sync_items_run_sync_key"),
    )
    op.create_index("ix_bim_revit_sync_items_run_id", "bim_revit_sync_items", ["run_id"], unique=False)
    op.create_index(
        "ix_bim_revit_sync_items_run_state",
        "bim_revit_sync_items",
        ["run_id", "state"],
        unique=False,
    )
    op.create_index("ix_bim_revit_sync_items_source_log_id", "bim_revit_sync_items", ["source_log_id"], unique=False)
    op.create_index("ix_bim_revit_sync_items_row_hash", "bim_revit_sync_items", ["row_hash"], unique=False)

    op.create_table(
        "bim_revit_client_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("client_model_guid", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("last_cursor", sa.String(length=64), nullable=True),
        sa.Column("last_manifest_at", sa.DateTime(), nullable=True),
        sa.Column("last_pull_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_code",
            "client_model_guid",
            "user_id",
            name="uq_bim_revit_client_state_project_model_user",
        ),
    )
    op.create_index(
        "ix_bim_revit_client_state_project_code",
        "bim_revit_client_state",
        ["project_code"],
        unique=False,
    )
    op.create_index(
        "ix_bim_revit_client_state_client_model_guid",
        "bim_revit_client_state",
        ["client_model_guid"],
        unique=False,
    )
    op.create_index("ix_bim_revit_client_state_user_id", "bim_revit_client_state", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("bim_revit_client_state")
    op.drop_table("bim_revit_sync_items")
    op.drop_table("bim_revit_sync_runs")
    op.drop_table("bim_equipment_items")
    op.drop_table("bim_mto_items")
    op.drop_table("bim_schedule_rows")
    op.drop_table("bim_schedule_runs")
    op.drop_table("bim_publish_items")
    op.drop_table("bim_publish_runs")
