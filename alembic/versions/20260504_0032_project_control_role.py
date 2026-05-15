"""Add project control role permissions.

Revision ID: 20260504_0032
Revises: 20260503_0031
Create Date: 2026-05-04 07:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.core.access_matrix import CANONICAL_PERMISSION_CATEGORIES, default_permission_matrix_for_category
from app.core.permission_catalog import permission_keys
from app.core.roles import ROLE_PERMISSIONS, Role


revision = "20260504_0032"
down_revision = "20260503_0031"
branch_labels = None
depends_on = None

ROLE = Role.PROJECT_CONTROL.value


def _insert_if_missing(bind, table, values: dict) -> None:
    filters = [
        table.c.role == values["role"],
        table.c.permission == values["permission"],
    ]
    if "category" in values:
        filters.insert(0, table.c.category == values["category"])
    exists = bind.execute(sa.select(table.c.permission).where(*filters).limit(1)).first()
    if exists:
        return
    bind.execute(sa.insert(table).values(**values))


def upgrade() -> None:
    bind = op.get_bind()
    role_table = sa.table(
        "role_permissions",
        sa.column("role", sa.String),
        sa.column("permission", sa.String),
        sa.column("allowed", sa.Boolean),
    )
    category_table = sa.table(
        "role_category_permissions",
        sa.column("category", sa.String),
        sa.column("role", sa.String),
        sa.column("permission", sa.String),
        sa.column("allowed", sa.Boolean),
    )

    role_defaults = {str(item) for item in ROLE_PERMISSIONS.get(Role.PROJECT_CONTROL, [])}
    for permission in permission_keys():
        _insert_if_missing(
            bind,
            role_table,
            {
                "role": ROLE,
                "permission": permission,
                "allowed": bool(permission in role_defaults),
            },
        )

    for category in CANONICAL_PERMISSION_CATEGORIES:
        baseline = default_permission_matrix_for_category(category)
        for permission in permission_keys():
            _insert_if_missing(
                bind,
                category_table,
                {
                    "category": category,
                    "role": ROLE,
                    "permission": permission,
                    "allowed": bool(baseline.get(ROLE, {}).get(permission, False)),
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_category_permissions WHERE role = :role"), {"role": ROLE})
    bind.execute(sa.text("DELETE FROM role_permissions WHERE role = :role"), {"role": ROLE})
