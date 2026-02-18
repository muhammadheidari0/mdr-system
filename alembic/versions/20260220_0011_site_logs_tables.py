"""Create site logs tables for dual workflow.

Revision ID: 20260220_0011
Revises: 20260220_0010
Create Date: 2026-02-20 10:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260220_0011"
down_revision = "20260220_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_log_workflow_statuses",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "site_log_sequences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("log_type", sa.String(length=32), nullable=False),
        sa.Column("log_date", sa.DateTime(), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_code", "log_type", "log_date", name="uq_site_log_sequences_project_type_date"),
    )

    op.create_table(
        "site_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("log_no", sa.String(length=128), nullable=False),
        sa.Column("log_type", sa.String(length=32), nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("discipline_code", sa.String(length=20), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("log_date", sa.DateTime(), nullable=False),
        sa.Column("weather", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status_code", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("submitted_by_id", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("verified_by_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["discipline_code"], ["disciplines.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("log_no", name="uq_site_logs_log_no"),
    )
    op.create_index("ix_site_logs_log_no", "site_logs", ["log_no"], unique=False)
    op.create_index("ix_site_logs_log_type", "site_logs", ["log_type"], unique=False)
    op.create_index("ix_site_logs_project_code", "site_logs", ["project_code"], unique=False)
    op.create_index("ix_site_logs_discipline_code", "site_logs", ["discipline_code"], unique=False)
    op.create_index("ix_site_logs_organization_id", "site_logs", ["organization_id"], unique=False)
    op.create_index("ix_site_logs_log_date", "site_logs", ["log_date"], unique=False)
    op.create_index("ix_site_logs_status_code", "site_logs", ["status_code"], unique=False)
    op.create_index("ix_site_logs_created_by_id", "site_logs", ["created_by_id"], unique=False)
    op.create_index("ix_site_logs_submitted_by_id", "site_logs", ["submitted_by_id"], unique=False)
    op.create_index("ix_site_logs_verified_by_id", "site_logs", ["verified_by_id"], unique=False)
    op.create_index(
        "ix_site_logs_project_disc_type_status_date",
        "site_logs",
        ["project_code", "discipline_code", "log_type", "status_code", "log_date"],
        unique=False,
    )
    op.create_index("ix_site_logs_status_date", "site_logs", ["status_code", "log_date"], unique=False)
    op.create_index("ix_site_logs_org_status", "site_logs", ["organization_id", "status_code"], unique=False)

    op.create_table(
        "site_log_manpower_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_log_id", sa.Integer(), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=True),
        sa.Column("role_label", sa.String(length=255), nullable=True),
        sa.Column("claimed_count", sa.Integer(), nullable=True),
        sa.Column("claimed_hours", sa.Float(), nullable=True),
        sa.Column("verified_count", sa.Integer(), nullable=True),
        sa.Column("verified_hours", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["site_log_id"], ["site_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_log_manpower_rows_site_log_id", "site_log_manpower_rows", ["site_log_id"], unique=False)
    op.create_index("ix_site_log_manpower_rows_site_role", "site_log_manpower_rows", ["site_log_id", "role_code"], unique=False)

    op.create_table(
        "site_log_equipment_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_log_id", sa.Integer(), nullable=False),
        sa.Column("equipment_code", sa.String(length=64), nullable=True),
        sa.Column("equipment_label", sa.String(length=255), nullable=True),
        sa.Column("claimed_status", sa.String(length=32), nullable=True),
        sa.Column("claimed_hours", sa.Float(), nullable=True),
        sa.Column("verified_status", sa.String(length=32), nullable=True),
        sa.Column("verified_hours", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["site_log_id"], ["site_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_log_equipment_rows_site_log_id", "site_log_equipment_rows", ["site_log_id"], unique=False)
    op.create_index("ix_site_log_equipment_rows_site_equipment", "site_log_equipment_rows", ["site_log_id", "equipment_code"], unique=False)

    op.create_table(
        "site_log_activity_rows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_log_id", sa.Integer(), nullable=False),
        sa.Column("activity_code", sa.String(length=64), nullable=True),
        sa.Column("activity_title", sa.String(length=255), nullable=True),
        sa.Column("source_system", sa.String(length=32), nullable=False, server_default="MANUAL"),
        sa.Column("external_ref", sa.String(length=128), nullable=True),
        sa.Column("claimed_progress_pct", sa.Float(), nullable=True),
        sa.Column("verified_progress_pct", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["site_log_id"], ["site_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_log_activity_rows_site_log_id", "site_log_activity_rows", ["site_log_id"], unique=False)
    op.create_index("ix_site_log_activity_rows_site_activity", "site_log_activity_rows", ["site_log_id", "activity_code"], unique=False)

    op.create_table(
        "site_log_status_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_log_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), nullable=True),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["site_log_id"], ["site_logs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_log_status_logs_site_log_id", "site_log_status_logs", ["site_log_id"], unique=False)
    op.create_index("ix_site_log_status_logs_site_changed_at", "site_log_status_logs", ["site_log_id", "changed_at"], unique=False)

    op.create_table(
        "site_log_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_log_id", sa.Integer(), nullable=False),
        sa.Column("comment_text", sa.Text(), nullable=False),
        sa.Column("comment_type", sa.String(length=32), nullable=False, server_default="comment"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["site_log_id"], ["site_logs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_log_comments_site_log_id", "site_log_comments", ["site_log_id"], unique=False)
    op.create_index("ix_site_log_comments_site_created_at", "site_log_comments", ["site_log_id", "created_at"], unique=False)

    op.create_table(
        "site_log_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_log_id", sa.Integer(), nullable=False),
        sa.Column("section_code", sa.String(length=32), nullable=False, server_default="GENERAL"),
        sa.Column("row_id", sa.Integer(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=1024), nullable=False),
        sa.Column("file_kind", sa.String(length=20), nullable=False, server_default="attachment"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("detected_mime", sa.String(length=128), nullable=True),
        sa.Column("validation_status", sa.String(length=32), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["site_log_id"], ["site_logs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_log_attachments_site_log_id", "site_log_attachments", ["site_log_id"], unique=False)
    op.create_index("ix_site_log_attachments_section_code", "site_log_attachments", ["section_code"], unique=False)
    op.create_index("ix_site_log_attachments_validation_status", "site_log_attachments", ["validation_status"], unique=False)
    op.create_index("ix_site_log_attachments_sha256", "site_log_attachments", ["sha256"], unique=False)
    op.create_index("ix_site_log_attachments_site_uploaded_at", "site_log_attachments", ["site_log_id", "uploaded_at"], unique=False)
    op.create_index("ix_site_log_attachments_site_section_uploaded_at", "site_log_attachments", ["site_log_id", "section_code", "uploaded_at"], unique=False)

    bind = op.get_bind()
    for code, label, sort_order in [
        ("DRAFT", "Draft", 10),
        ("SUBMITTED", "Submitted", 20),
        ("VERIFIED", "Verified", 30),
    ]:
        bind.execute(
            sa.text(
                """
                INSERT INTO site_log_workflow_statuses (code, label, sort_order, is_active)
                VALUES (:code, :label, :sort_order, TRUE)
                """
            ),
            {"code": code, "label": label, "sort_order": int(sort_order)},
        )


def downgrade() -> None:
    op.drop_table("site_log_attachments")
    op.drop_table("site_log_comments")
    op.drop_table("site_log_status_logs")
    op.drop_table("site_log_activity_rows")
    op.drop_table("site_log_equipment_rows")
    op.drop_table("site_log_manpower_rows")
    op.drop_table("site_logs")
    op.drop_table("site_log_sequences")
    op.drop_table("site_log_workflow_statuses")
