"""Add PMS templates and activity mappings for site logs.

Revision ID: 20260505_0036
Revises: 20260504_0035
Create Date: 2026-05-05 10:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260505_0036"
down_revision = "20260504_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_log_pms_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_site_log_pms_templates_code"),
    )
    op.create_index("ix_site_log_pms_templates_code", "site_log_pms_templates", ["code"])
    op.create_index(
        "ix_site_log_pms_templates_active_sort",
        "site_log_pms_templates",
        ["is_active", "sort_order"],
    )

    op.create_table(
        "site_log_pms_template_steps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("step_code", sa.String(length=64), nullable=False),
        sa.Column("step_title", sa.String(length=255), nullable=False),
        sa.Column("weight_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["template_id"], ["site_log_pms_templates.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("template_id", "step_code", name="uq_site_log_pms_template_steps_template_code"),
    )
    op.create_index(
        "ix_site_log_pms_template_steps_template_sort",
        "site_log_pms_template_steps",
        ["template_id", "sort_order"],
    )

    op.create_table(
        "site_log_activity_pms_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("activity_catalog_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("template_code", sa.String(length=64), nullable=False),
        sa.Column("template_title", sa.String(length=255), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["activity_catalog_id"], ["site_log_activity_catalog.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["site_log_pms_templates.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("activity_catalog_id", name="uq_site_log_activity_pms_mappings_activity"),
    )
    op.create_index(
        "ix_site_log_activity_pms_mappings_activity_catalog_id",
        "site_log_activity_pms_mappings",
        ["activity_catalog_id"],
    )
    op.create_index(
        "ix_site_log_activity_pms_mappings_template",
        "site_log_activity_pms_mappings",
        ["template_id"],
    )

    op.create_table(
        "site_log_activity_pms_steps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mapping_id", sa.Integer(), nullable=False),
        sa.Column("source_template_step_id", sa.Integer(), nullable=True),
        sa.Column("step_code", sa.String(length=64), nullable=False),
        sa.Column("step_title", sa.String(length=255), nullable=False),
        sa.Column("weight_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["mapping_id"], ["site_log_activity_pms_mappings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_template_step_id"], ["site_log_pms_template_steps.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("mapping_id", "step_code", name="uq_site_log_activity_pms_steps_mapping_code"),
    )
    op.create_index(
        "ix_site_log_activity_pms_steps_mapping_sort",
        "site_log_activity_pms_steps",
        ["mapping_id", "sort_order"],
    )

    with op.batch_alter_table("site_log_activity_rows") as batch_op:
        batch_op.add_column(sa.Column("pms_mapping_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("pms_template_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("pms_template_title", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("pms_template_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("pms_step_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("pms_step_title", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("pms_step_weight_pct", sa.Float(), nullable=True))
        batch_op.create_foreign_key(
            "fk_site_log_activity_rows_pms_mapping",
            "site_log_activity_pms_mappings",
            ["pms_mapping_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_site_log_activity_rows_pms_mapping_id", ["pms_mapping_id"])


def downgrade() -> None:
    with op.batch_alter_table("site_log_activity_rows") as batch_op:
        batch_op.drop_index("ix_site_log_activity_rows_pms_mapping_id")
        batch_op.drop_constraint("fk_site_log_activity_rows_pms_mapping", type_="foreignkey")
        batch_op.drop_column("pms_step_weight_pct")
        batch_op.drop_column("pms_step_title")
        batch_op.drop_column("pms_step_code")
        batch_op.drop_column("pms_template_version")
        batch_op.drop_column("pms_template_title")
        batch_op.drop_column("pms_template_code")
        batch_op.drop_column("pms_mapping_id")

    op.drop_index("ix_site_log_activity_pms_steps_mapping_sort", table_name="site_log_activity_pms_steps")
    op.drop_table("site_log_activity_pms_steps")
    op.drop_index("ix_site_log_activity_pms_mappings_template", table_name="site_log_activity_pms_mappings")
    op.drop_index("ix_site_log_activity_pms_mappings_activity_catalog_id", table_name="site_log_activity_pms_mappings")
    op.drop_table("site_log_activity_pms_mappings")
    op.drop_index("ix_site_log_pms_template_steps_template_sort", table_name="site_log_pms_template_steps")
    op.drop_table("site_log_pms_template_steps")
    op.drop_index("ix_site_log_pms_templates_active_sort", table_name="site_log_pms_templates")
    op.drop_index("ix_site_log_pms_templates_code", table_name="site_log_pms_templates")
    op.drop_table("site_log_pms_templates")
