"""Add site log activity catalog, report sections, and QC snapshot fields.

Revision ID: 20260501_0029
Revises: 20260501_0028
Create Date: 2026-05-01 15:35:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260501_0029"
down_revision = "20260501_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("site_logs") as batch_op:
        batch_op.add_column(sa.Column("organization_contract_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("qc_test_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("qc_inspection_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("qc_open_ncr_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("qc_open_punch_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("qc_summary_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("qc_snapshot_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_site_logs_organization_contract_id", ["organization_contract_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_site_logs_organization_contract_id",
            "organization_contracts",
            ["organization_contract_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "site_log_activity_catalog",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("organization_contract_id", sa.Integer(), nullable=True),
        sa.Column("activity_code", sa.String(length=64), nullable=False),
        sa.Column("activity_title", sa.String(length=255), nullable=False),
        sa.Column("default_location", sa.String(length=255), nullable=True),
        sa.Column("default_unit", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_contract_id"], ["organization_contracts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "project_code",
            "organization_id",
            "organization_contract_id",
            "activity_code",
            name="uq_site_log_activity_catalog_scope_code",
        ),
    )
    op.create_index(
        "ix_site_log_activity_catalog_project_sort",
        "site_log_activity_catalog",
        ["project_code", "sort_order"],
        unique=False,
    )
    op.create_index(
        "ix_site_log_activity_catalog_org",
        "site_log_activity_catalog",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_site_log_activity_catalog_contract",
        "site_log_activity_catalog",
        ["organization_contract_id"],
        unique=False,
    )

    op.create_table(
        "site_log_material_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("site_log_id", sa.Integer(), nullable=False),
        sa.Column("material_code", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("incoming_quantity", sa.Float(), nullable=True),
        sa.Column("consumed_quantity", sa.Float(), nullable=True),
        sa.Column("cumulative_quantity", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["site_log_id"], ["site_logs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_site_log_material_rows_site_code",
        "site_log_material_rows",
        ["site_log_id", "material_code"],
        unique=False,
    )

    op.create_table(
        "site_log_issue_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("site_log_id", sa.Integer(), nullable=False),
        sa.Column("issue_type", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("responsible_party", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["site_log_id"], ["site_logs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_site_log_issue_rows_site_type",
        "site_log_issue_rows",
        ["site_log_id", "issue_type"],
        unique=False,
    )

    op.create_table(
        "site_log_attachment_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("site_log_id", sa.Integer(), nullable=False),
        sa.Column("attachment_type", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("reference_no", sa.String(length=128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("linked_attachment_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["site_log_id"], ["site_logs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_attachment_id"], ["site_log_attachments.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_site_log_attachment_rows_site_type",
        "site_log_attachment_rows",
        ["site_log_id", "attachment_type"],
        unique=False,
    )
    op.create_index(
        "ix_site_log_attachment_rows_linked_attachment",
        "site_log_attachment_rows",
        ["linked_attachment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_site_log_attachment_rows_linked_attachment", table_name="site_log_attachment_rows")
    op.drop_index("ix_site_log_attachment_rows_site_type", table_name="site_log_attachment_rows")
    op.drop_table("site_log_attachment_rows")

    op.drop_index("ix_site_log_issue_rows_site_type", table_name="site_log_issue_rows")
    op.drop_table("site_log_issue_rows")

    op.drop_index("ix_site_log_material_rows_site_code", table_name="site_log_material_rows")
    op.drop_table("site_log_material_rows")

    op.drop_index("ix_site_log_activity_catalog_contract", table_name="site_log_activity_catalog")
    op.drop_index("ix_site_log_activity_catalog_org", table_name="site_log_activity_catalog")
    op.drop_index("ix_site_log_activity_catalog_project_sort", table_name="site_log_activity_catalog")
    op.drop_table("site_log_activity_catalog")

    with op.batch_alter_table("site_logs") as batch_op:
        batch_op.drop_constraint("fk_site_logs_organization_contract_id", type_="foreignkey")
        batch_op.drop_index("ix_site_logs_organization_contract_id")
        batch_op.drop_column("qc_snapshot_at")
        batch_op.drop_column("qc_summary_note")
        batch_op.drop_column("qc_open_punch_count")
        batch_op.drop_column("qc_open_ncr_count")
        batch_op.drop_column("qc_inspection_count")
        batch_op.drop_column("qc_test_count")
        batch_op.drop_column("organization_contract_id")
