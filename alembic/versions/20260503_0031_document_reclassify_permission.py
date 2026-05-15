"""Add document reclassify permission.

Revision ID: 20260503_0031
Revises: 20260502_0030
Create Date: 2026-05-03 22:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.core.access_matrix import CANONICAL_MATRIX_ROLES, CANONICAL_PERMISSION_CATEGORIES
from app.core.roles import ALL_ROLES, Role


revision = "20260503_0031"
down_revision = "20260502_0030"
branch_labels = None
depends_on = None

PERMISSION = "documents:reclassify"
DEFAULT_ALLOWED = {Role.ADMIN.value, Role.MANAGER.value, Role.DCC.value}


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

    for role in ALL_ROLES:
        _insert_if_missing(
            bind,
            role_table,
            {
                "role": role,
                "permission": PERMISSION,
                "allowed": bool(role in DEFAULT_ALLOWED),
            },
        )

    for category in CANONICAL_PERMISSION_CATEGORIES:
        for role in CANONICAL_MATRIX_ROLES:
            _insert_if_missing(
                bind,
                category_table,
                {
                    "category": category,
                    "role": role,
                    "permission": PERMISSION,
                    "allowed": bool(role in {Role.MANAGER.value, Role.DCC.value}),
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_category_permissions WHERE permission = :permission"), {"permission": PERMISSION})
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission = :permission"), {"permission": PERMISSION})
