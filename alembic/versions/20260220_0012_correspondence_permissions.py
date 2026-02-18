"""Backfill correspondence permissions for matrix-driven access.

Revision ID: 20260220_0012
Revises: 20260220_0011
Create Date: 2026-02-20 10:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260220_0012"
down_revision = "20260220_0011"
branch_labels = None
depends_on = None


PERMISSIONS: tuple[str, ...] = (
    "correspondence:read",
    "correspondence:create",
    "correspondence:update",
    "correspondence:delete",
)

CATEGORIES: tuple[str, ...] = (
    "employer",
    "consultant",
    "contractor",
)

ROLE_ALLOWED: dict[str, set[str]] = {
    "admin": set(PERMISSIONS),
    "manager": set(PERMISSIONS),
    "dcc": set(PERMISSIONS),
    "user": set(PERMISSIONS),
    "viewer": {"correspondence:read"},
}


def _insert_role_permission_if_missing(
    bind: sa.engine.Connection,
    *,
    role: str,
    permission: str,
    allowed: bool,
) -> None:
    exists = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM role_permissions
            WHERE role = :role AND permission = :permission
            LIMIT 1
            """
        ),
        {"role": role, "permission": permission},
    ).first()
    if exists:
        return
    bind.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role, permission, allowed)
            VALUES (:role, :permission, :allowed)
            """
        ),
        {"role": role, "permission": permission, "allowed": bool(allowed)},
    )


def _insert_role_category_permission_if_missing(
    bind: sa.engine.Connection,
    *,
    category: str,
    role: str,
    permission: str,
    allowed: bool,
) -> None:
    exists = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM role_category_permissions
            WHERE category = :category
              AND role = :role
              AND permission = :permission
            LIMIT 1
            """
        ),
        {
            "category": category,
            "role": role,
            "permission": permission,
        },
    ).first()
    if exists:
        return
    bind.execute(
        sa.text(
            """
            INSERT INTO role_category_permissions (category, role, permission, allowed)
            VALUES (:category, :role, :permission, :allowed)
            """
        ),
        {
            "category": category,
            "role": role,
            "permission": permission,
            "allowed": bool(allowed),
        },
    )


def upgrade() -> None:
    bind = op.get_bind()

    for role, allowed_permissions in ROLE_ALLOWED.items():
        for permission in PERMISSIONS:
            _insert_role_permission_if_missing(
                bind,
                role=role,
                permission=permission,
                allowed=permission in allowed_permissions,
            )

    for category in CATEGORIES:
        for role, allowed_permissions in ROLE_ALLOWED.items():
            for permission in PERMISSIONS:
                _insert_role_category_permission_if_missing(
                    bind,
                    category=category,
                    role=role,
                    permission=permission,
                    allowed=permission in allowed_permissions,
                )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM role_category_permissions
            WHERE permission IN (
                'correspondence:read',
                'correspondence:create',
                'correspondence:update',
                'correspondence:delete'
            )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission IN (
                'correspondence:read',
                'correspondence:create',
                'correspondence:update',
                'correspondence:delete'
            )
            """
        )
    )
