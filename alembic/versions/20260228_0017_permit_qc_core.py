"""Add permit QC module core tables.

Revision ID: 20260228_0017
Revises: 20260225_0016
Create Date: 2026-02-28 14:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260228_0017"
down_revision = "20260225_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "permit_qc_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_code", sa.String(length=50), nullable=True),
        sa.Column("discipline_code", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["discipline_code"], ["disciplines.code"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_permit_qc_templates_code", "permit_qc_templates", ["code"], unique=True)
    op.create_index("ix_permit_qc_templates_active", "permit_qc_templates", ["is_active"], unique=False)
    op.create_index(
        "ix_permit_qc_templates_project_discipline",
        "permit_qc_templates",
        ["project_code", "discipline_code"],
        unique=False,
    )

    op.create_table(
        "permit_qc_template_stations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("station_key", sa.String(length=64), nullable=False),
        sa.Column("station_label", sa.String(length=255), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["template_id"], ["permit_qc_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("template_id", "station_key", name="uq_permit_qc_template_station_key"),
    )
    op.create_index(
        "ix_permit_qc_template_stations_template_sort",
        "permit_qc_template_stations",
        ["template_id", "sort_order"],
        unique=False,
    )
    op.create_index(
        "ix_permit_qc_template_stations_organization_id",
        "permit_qc_template_stations",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "permit_qc_template_checks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("check_code", sa.String(length=64), nullable=False),
        sa.Column("check_label", sa.String(length=255), nullable=False),
        sa.Column("check_type", sa.String(length=32), nullable=False, server_default="BOOLEAN"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["station_id"], ["permit_qc_template_stations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("station_id", "check_code", name="uq_permit_qc_template_check_code"),
    )
    op.create_index(
        "ix_permit_qc_template_checks_station_sort",
        "permit_qc_template_checks",
        ["station_id", "sort_order"],
        unique=False,
    )

    op.create_table(
        "permit_qc_permits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("permit_no", sa.String(length=128), nullable=False),
        sa.Column("permit_date", sa.DateTime(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("wall_name", sa.String(length=255), nullable=True),
        sa.Column("floor_label", sa.String(length=64), nullable=True),
        sa.Column("elevation_start", sa.String(length=64), nullable=True),
        sa.Column("elevation_end", sa.String(length=64), nullable=True),
        sa.Column("status_code", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("discipline_code", sa.String(length=20), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("contractor_org_id", sa.Integer(), nullable=True),
        sa.Column("consultant_org_id", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["discipline_code"], ["disciplines.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_id"], ["permit_qc_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contractor_org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["consultant_org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_code", "permit_no", name="uq_permit_qc_permit_project_no"),
    )
    op.create_index("ix_permit_qc_permits_permit_no", "permit_qc_permits", ["permit_no"], unique=False)
    op.create_index("ix_permit_qc_permits_status", "permit_qc_permits", ["status_code"], unique=False)
    op.create_index("ix_permit_qc_permits_permit_date", "permit_qc_permits", ["permit_date"], unique=False)
    op.create_index(
        "ix_permit_qc_permits_project_disc",
        "permit_qc_permits",
        ["project_code", "discipline_code"],
        unique=False,
    )
    op.create_index(
        "ix_permit_qc_permits_org_status",
        "permit_qc_permits",
        ["organization_id", "status_code"],
        unique=False,
    )

    op.create_table(
        "permit_qc_permit_stations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("permit_id", sa.Integer(), nullable=False),
        sa.Column("template_station_id", sa.Integer(), nullable=True),
        sa.Column("station_key", sa.String(length=64), nullable=False),
        sa.Column("station_label", sa.String(length=255), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status_code", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["permit_id"], ["permit_qc_permits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_station_id"], ["permit_qc_template_stations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_permit_qc_permit_stations_permit_sort",
        "permit_qc_permit_stations",
        ["permit_id", "sort_order"],
        unique=False,
    )
    op.create_index(
        "ix_permit_qc_permit_stations_status",
        "permit_qc_permit_stations",
        ["status_code"],
        unique=False,
    )

    op.create_table(
        "permit_qc_permit_checks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("permit_station_id", sa.Integer(), nullable=False),
        sa.Column("template_check_id", sa.Integer(), nullable=True),
        sa.Column("check_code", sa.String(length=64), nullable=False),
        sa.Column("check_label", sa.String(length=255), nullable=False),
        sa.Column("check_type", sa.String(length=32), nullable=False, server_default="BOOLEAN"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_bool", sa.Boolean(), nullable=True),
        sa.Column("value_number", sa.Float(), nullable=True),
        sa.Column("value_date", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["permit_station_id"], ["permit_qc_permit_stations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_check_id"], ["permit_qc_template_checks.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_permit_qc_permit_checks_station_sort",
        "permit_qc_permit_checks",
        ["permit_station_id", "sort_order"],
        unique=False,
    )

    op.create_table(
        "permit_qc_permit_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("permit_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=1024), nullable=False),
        sa.Column("file_kind", sa.String(length=20), nullable=False, server_default="attachment"),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("detected_mime", sa.String(length=128), nullable=True),
        sa.Column("validation_status", sa.String(length=32), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_backend", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["permit_id"], ["permit_qc_permits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_permit_qc_permit_attachments_permit",
        "permit_qc_permit_attachments",
        ["permit_id"],
        unique=False,
    )
    op.create_index(
        "ix_permit_qc_permit_attachments_uploaded_at",
        "permit_qc_permit_attachments",
        ["uploaded_at"],
        unique=False,
    )
    op.create_index(
        "ix_permit_qc_permit_attachments_sha256",
        "permit_qc_permit_attachments",
        ["sha256"],
        unique=False,
    )
    op.create_index(
        "ix_permit_qc_permit_attachments_validation_status",
        "permit_qc_permit_attachments",
        ["validation_status"],
        unique=False,
    )

    op.create_table(
        "permit_qc_permit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("permit_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status_code", sa.String(length=32), nullable=True),
        sa.Column("to_status_code", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["permit_id"], ["permit_qc_permits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["station_id"], ["permit_qc_permit_stations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_permit_qc_permit_events_permit_created",
        "permit_qc_permit_events",
        ["permit_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_permit_qc_permit_events_type",
        "permit_qc_permit_events",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_permit_qc_permit_events_type", table_name="permit_qc_permit_events")
    op.drop_index("ix_permit_qc_permit_events_permit_created", table_name="permit_qc_permit_events")
    op.drop_table("permit_qc_permit_events")

    op.drop_index("ix_permit_qc_permit_attachments_validation_status", table_name="permit_qc_permit_attachments")
    op.drop_index("ix_permit_qc_permit_attachments_sha256", table_name="permit_qc_permit_attachments")
    op.drop_index("ix_permit_qc_permit_attachments_uploaded_at", table_name="permit_qc_permit_attachments")
    op.drop_index("ix_permit_qc_permit_attachments_permit", table_name="permit_qc_permit_attachments")
    op.drop_table("permit_qc_permit_attachments")

    op.drop_index("ix_permit_qc_permit_checks_station_sort", table_name="permit_qc_permit_checks")
    op.drop_table("permit_qc_permit_checks")

    op.drop_index("ix_permit_qc_permit_stations_status", table_name="permit_qc_permit_stations")
    op.drop_index("ix_permit_qc_permit_stations_permit_sort", table_name="permit_qc_permit_stations")
    op.drop_table("permit_qc_permit_stations")

    op.drop_index("ix_permit_qc_permits_org_status", table_name="permit_qc_permits")
    op.drop_index("ix_permit_qc_permits_project_disc", table_name="permit_qc_permits")
    op.drop_index("ix_permit_qc_permits_permit_date", table_name="permit_qc_permits")
    op.drop_index("ix_permit_qc_permits_status", table_name="permit_qc_permits")
    op.drop_index("ix_permit_qc_permits_permit_no", table_name="permit_qc_permits")
    op.drop_table("permit_qc_permits")

    op.drop_index("ix_permit_qc_template_checks_station_sort", table_name="permit_qc_template_checks")
    op.drop_table("permit_qc_template_checks")

    op.drop_index("ix_permit_qc_template_stations_organization_id", table_name="permit_qc_template_stations")
    op.drop_index("ix_permit_qc_template_stations_template_sort", table_name="permit_qc_template_stations")
    op.drop_table("permit_qc_template_stations")

    op.drop_index("ix_permit_qc_templates_project_discipline", table_name="permit_qc_templates")
    op.drop_index("ix_permit_qc_templates_active", table_name="permit_qc_templates")
    op.drop_index("ix_permit_qc_templates_code", table_name="permit_qc_templates")
    op.drop_table("permit_qc_templates")
