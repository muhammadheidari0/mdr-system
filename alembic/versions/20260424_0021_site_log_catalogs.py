"""Add site log catalogs for role, equipment, and equipment status.

Revision ID: 20260424_0021
Revises: 20260423_0020
Create Date: 2026-04-24 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260424_0021"
down_revision = "20260423_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create site_log_role_catalog table
    op.create_table(
        "site_log_role_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_site_log_role_catalog_code"),
    )
    op.create_index("ix_site_log_role_catalog_code", "site_log_role_catalog", ["code"])

    # Create site_log_equipment_catalog table
    op.create_table(
        "site_log_equipment_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_site_log_equipment_catalog_code"),
    )
    op.create_index("ix_site_log_equipment_catalog_code", "site_log_equipment_catalog", ["code"])

    # Create site_log_equipment_status_catalog table
    op.create_table(
        "site_log_equipment_status_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_site_log_equipment_status_catalog_code"),
    )
    op.create_index("ix_site_log_equipment_status_catalog_code", "site_log_equipment_status_catalog", ["code"])

    # Seed initial data for roles
    op.execute(
        """
        INSERT INTO site_log_role_catalog (code, label, sort_order, is_active) VALUES
        ('WELD', 'جوشکار', 10, true),
        ('PIPE', 'لوله‌کش', 20, true),
        ('ELEC', 'برقکار', 30, true),
        ('MECH', 'مکانیک', 40, true),
        ('LABOR', 'کارگر ساده', 50, true),
        ('SUPERVISOR', 'سرکارگر', 60, true),
        ('SAFETY', 'ایمنی', 70, true);
        """
    )

    # Seed initial data for equipment
    op.execute(
        """
        INSERT INTO site_log_equipment_catalog (code, label, sort_order, is_active) VALUES
        ('CRANE', 'جرثقیل', 10, true),
        ('LOADER', 'لودر', 20, true),
        ('EXCAVATOR', 'بیل‌مکانیکی', 30, true),
        ('TRUCK', 'کامیون', 40, true),
        ('COMPRESSOR', 'کمپرسور', 50, true),
        ('GENERATOR', 'ژنراتور', 60, true);
        """
    )

    # Seed initial data for equipment status
    op.execute(
        """
        INSERT INTO site_log_equipment_status_catalog (code, label, sort_order, is_active) VALUES
        ('ACTIVE', 'فعال', 10, true),
        ('IDLE', 'بیکار', 20, true),
        ('REPAIR', 'در تعمیر', 30, true),
        ('STANDBY', 'آماده‌باش', 40, true);
        """
    )


def downgrade() -> None:
    op.drop_index("ix_site_log_equipment_status_catalog_code", "site_log_equipment_status_catalog")
    op.drop_table("site_log_equipment_status_catalog")
    op.drop_index("ix_site_log_equipment_catalog_code", "site_log_equipment_catalog")
    op.drop_table("site_log_equipment_catalog")
    op.drop_index("ix_site_log_role_catalog_code", "site_log_role_catalog")
    op.drop_table("site_log_role_catalog")
