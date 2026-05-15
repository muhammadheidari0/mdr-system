"""Seed canonical category permission rows.

Revision ID: 20260428_0023
Revises: 20260425_0022
Create Date: 2026-04-28 10:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.core.access_matrix import CANONICAL_MATRIX_ROLES, CANONICAL_PERMISSION_CATEGORIES, default_permission_matrix_for_category
from app.core.permission_catalog import permission_keys


revision = "20260428_0023"
down_revision = "20260425_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    table = sa.table(
        "role_category_permissions",
        sa.column("id", sa.Integer),
        sa.column("category", sa.String),
        sa.column("role", sa.String),
        sa.column("permission", sa.String),
        sa.column("allowed", sa.Boolean),
    )
    existing = {
        (str(row[0] or "").strip().lower(), str(row[1] or "").strip().lower(), str(row[2] or "").strip())
        for row in bind.execute(
            sa.select(table.c.category, table.c.role, table.c.permission)
        ).all()
    }

    for category in CANONICAL_PERMISSION_CATEGORIES:
        baseline = default_permission_matrix_for_category(category)
        for role in CANONICAL_MATRIX_ROLES:
            for permission in permission_keys():
                key = (category, role, permission)
                if key in existing:
                    continue
                bind.execute(
                    sa.insert(table).values(
                        category=category,
                        role=role,
                        permission=permission,
                        allowed=bool(baseline.get(role, {}).get(permission, False)),
                    )
                )


def downgrade() -> None:
    # Data seeding is intentionally non-reversible.
    pass
