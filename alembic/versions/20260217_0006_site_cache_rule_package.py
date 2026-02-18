"""Add package_code filter column to site cache pin rules.

Revision ID: 20260217_0006
Revises: 20260216_0005
Create Date: 2026-02-17 09:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260217_0006"
down_revision = "20260216_0005"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(str(col.get("name")) == column_name for col in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(str(idx.get("name")) == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "site_cache_pin_rules"):
        return

    if not _column_exists(inspector, "site_cache_pin_rules", "package_code"):
        op.add_column(
            "site_cache_pin_rules",
            sa.Column("package_code", sa.String(length=30), nullable=True),
        )
        inspector = sa.inspect(bind)

    if not _index_exists(inspector, "site_cache_pin_rules", "ix_site_cache_pin_rules_package"):
        op.create_index(
            "ix_site_cache_pin_rules_package",
            "site_cache_pin_rules",
            ["package_code"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "site_cache_pin_rules"):
        return

    if _index_exists(inspector, "site_cache_pin_rules", "ix_site_cache_pin_rules_package"):
        op.drop_index("ix_site_cache_pin_rules_package", table_name="site_cache_pin_rules")
        inspector = sa.inspect(bind)

    if _column_exists(inspector, "site_cache_pin_rules", "package_code"):
        op.drop_column("site_cache_pin_rules", "package_code")
