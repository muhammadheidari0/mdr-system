"""Add BIM inbox workflow columns and indexes.

Revision ID: 20260225_0016
Revises: 20260223_0015
Create Date: 2026-02-25 16:40:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260225_0016"
down_revision = "20260223_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bim_publish_runs",
        sa.Column("ingestion_mode", sa.String(length=32), nullable=False, server_default="legacy_direct"),
    )
    op.add_column("bim_publish_runs", sa.Column("staging_status", sa.String(length=32), nullable=True))
    op.add_column("bim_publish_runs", sa.Column("validation_status", sa.String(length=32), nullable=True))
    op.add_column("bim_publish_runs", sa.Column("approved_by_id", sa.Integer(), nullable=True))
    op.add_column("bim_publish_runs", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.add_column("bim_publish_runs", sa.Column("rejected_by_id", sa.Integer(), nullable=True))
    op.add_column("bim_publish_runs", sa.Column("rejected_at", sa.DateTime(), nullable=True))
    op.add_column("bim_publish_runs", sa.Column("reject_reason", sa.Text(), nullable=True))
    op.add_column("bim_publish_runs", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column("bim_publish_runs", sa.Column("plugin_key_id", sa.String(length=128), nullable=True))

    op.create_foreign_key(
        "fk_bim_publish_runs_approved_by_id_users",
        "bim_publish_runs",
        "users",
        ["approved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_bim_publish_runs_rejected_by_id_users",
        "bim_publish_runs",
        "users",
        ["rejected_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_bim_publish_runs_ingestion_mode", "bim_publish_runs", ["ingestion_mode"], unique=False)
    op.create_index("ix_bim_publish_runs_staging_status", "bim_publish_runs", ["staging_status"], unique=False)
    op.create_index("ix_bim_publish_runs_expires_at", "bim_publish_runs", ["expires_at"], unique=False)
    op.create_index("ix_bim_publish_runs_plugin_key_id", "bim_publish_runs", ["plugin_key_id"], unique=False)

    op.add_column("bim_publish_items", sa.Column("staging_file_path", sa.String(length=1024), nullable=True))
    op.add_column("bim_publish_items", sa.Column("staging_sha256", sa.String(length=64), nullable=True))
    op.add_column("bim_publish_items", sa.Column("validation_state", sa.String(length=32), nullable=True))
    op.add_column("bim_publish_items", sa.Column("validation_errors_json", sa.Text(), nullable=True))
    op.add_column("bim_publish_items", sa.Column("archive_document_id", sa.Integer(), nullable=True))
    op.add_column("bim_publish_items", sa.Column("archive_file_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_bim_publish_items_archive_document_id_mdr_documents",
        "bim_publish_items",
        "mdr_documents",
        ["archive_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_bim_publish_items_archive_file_id_archive_files",
        "bim_publish_items",
        "archive_files",
        ["archive_file_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_bim_publish_items_staging_sha256", "bim_publish_items", ["staging_sha256"], unique=False)
    op.create_index("ix_bim_publish_items_validation_state", "bim_publish_items", ["validation_state"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bim_publish_items_validation_state", table_name="bim_publish_items")
    op.drop_index("ix_bim_publish_items_staging_sha256", table_name="bim_publish_items")
    op.drop_constraint("fk_bim_publish_items_archive_file_id_archive_files", "bim_publish_items", type_="foreignkey")
    op.drop_constraint("fk_bim_publish_items_archive_document_id_mdr_documents", "bim_publish_items", type_="foreignkey")
    op.drop_column("bim_publish_items", "archive_file_id")
    op.drop_column("bim_publish_items", "archive_document_id")
    op.drop_column("bim_publish_items", "validation_errors_json")
    op.drop_column("bim_publish_items", "validation_state")
    op.drop_column("bim_publish_items", "staging_sha256")
    op.drop_column("bim_publish_items", "staging_file_path")

    op.drop_index("ix_bim_publish_runs_plugin_key_id", table_name="bim_publish_runs")
    op.drop_index("ix_bim_publish_runs_expires_at", table_name="bim_publish_runs")
    op.drop_index("ix_bim_publish_runs_staging_status", table_name="bim_publish_runs")
    op.drop_index("ix_bim_publish_runs_ingestion_mode", table_name="bim_publish_runs")
    op.drop_constraint("fk_bim_publish_runs_rejected_by_id_users", "bim_publish_runs", type_="foreignkey")
    op.drop_constraint("fk_bim_publish_runs_approved_by_id_users", "bim_publish_runs", type_="foreignkey")
    op.drop_column("bim_publish_runs", "plugin_key_id")
    op.drop_column("bim_publish_runs", "expires_at")
    op.drop_column("bim_publish_runs", "reject_reason")
    op.drop_column("bim_publish_runs", "rejected_at")
    op.drop_column("bim_publish_runs", "rejected_by_id")
    op.drop_column("bim_publish_runs", "approved_at")
    op.drop_column("bim_publish_runs", "approved_by_id")
    op.drop_column("bim_publish_runs", "validation_status")
    op.drop_column("bim_publish_runs", "staging_status")
    op.drop_column("bim_publish_runs", "ingestion_mode")

