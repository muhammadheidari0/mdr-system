"""Split internal module settings visibility into per-hub permissions.

Revision ID: 20260429_0024
Revises: 20260428_0023
Create Date: 2026-04-29 14:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.core.access_matrix import (
    CANONICAL_MATRIX_ROLES,
    CANONICAL_PERMISSION_CATEGORIES,
    default_permission_matrix_for_category,
)
from app.core.roles import ALL_ROLES, ROLE_PERMISSIONS, Role


revision = "20260429_0024"
down_revision = "20260428_0023"
branch_labels = None
depends_on = None

OLD_PERMISSION = "module_settings:read"
NEW_PERMISSIONS: tuple[str, ...] = (
    "module_settings_edms:read",
    "module_settings_contractor:read",
    "module_settings_consultant:read",
)


def _role_default_allowed(role: str, permission: str) -> bool:
    try:
        role_enum = Role(str(role or "").strip().lower())
    except Exception:
        return False
    allowed = {str(item) for item in (ROLE_PERMISSIONS.get(role_enum, []) or []) if str(item or "").strip()}
    return "*" in allowed or permission in allowed


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

    existing_role_rows = {
        (str(role or "").strip().lower(), str(permission or "").strip()): bool(allowed)
        for role, permission, allowed in bind.execute(
            sa.select(role_table.c.role, role_table.c.permission, role_table.c.allowed)
        ).all()
    }
    for role in ALL_ROLES:
        source_allowed = existing_role_rows.get((role, OLD_PERMISSION))
        for permission in NEW_PERMISSIONS:
            if (role, permission) in existing_role_rows:
                continue
            allowed = source_allowed if source_allowed is not None else _role_default_allowed(role, permission)
            bind.execute(
                sa.insert(role_table).values(
                    role=role,
                    permission=permission,
                    allowed=bool(allowed),
                )
            )
    bind.execute(sa.delete(role_table).where(role_table.c.permission == OLD_PERMISSION))

    existing_category_rows = {
        (
            str(category or "").strip().lower(),
            str(role or "").strip().lower(),
            str(permission or "").strip(),
        ): bool(allowed)
        for category, role, permission, allowed in bind.execute(
            sa.select(
                category_table.c.category,
                category_table.c.role,
                category_table.c.permission,
                category_table.c.allowed,
            )
        ).all()
    }
    for category in CANONICAL_PERMISSION_CATEGORIES:
        baseline = default_permission_matrix_for_category(category)
        for role in CANONICAL_MATRIX_ROLES:
            source_allowed = existing_category_rows.get((category, role, OLD_PERMISSION))
            for permission in NEW_PERMISSIONS:
                if (category, role, permission) in existing_category_rows:
                    continue
                allowed = source_allowed if source_allowed is not None else bool(
                    baseline.get(role, {}).get(permission, False)
                )
                bind.execute(
                    sa.insert(category_table).values(
                        category=category,
                        role=role,
                        permission=permission,
                        allowed=bool(allowed),
                    )
                )
    bind.execute(sa.delete(category_table).where(category_table.c.permission == OLD_PERMISSION))


def downgrade() -> None:
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

    existing_role_rows = {
        (str(role or "").strip().lower(), str(permission or "").strip()): bool(allowed)
        for role, permission, allowed in bind.execute(
            sa.select(role_table.c.role, role_table.c.permission, role_table.c.allowed)
        ).all()
    }
    for role in ALL_ROLES:
        if (role, OLD_PERMISSION) in existing_role_rows:
            continue
        allowed = all(existing_role_rows.get((role, permission), False) for permission in NEW_PERMISSIONS)
        bind.execute(
            sa.insert(role_table).values(
                role=role,
                permission=OLD_PERMISSION,
                allowed=bool(allowed),
            )
        )
    bind.execute(sa.delete(role_table).where(role_table.c.permission.in_(NEW_PERMISSIONS)))

    existing_category_rows = {
        (
            str(category or "").strip().lower(),
            str(role or "").strip().lower(),
            str(permission or "").strip(),
        ): bool(allowed)
        for category, role, permission, allowed in bind.execute(
            sa.select(
                category_table.c.category,
                category_table.c.role,
                category_table.c.permission,
                category_table.c.allowed,
            )
        ).all()
    }
    for category in CANONICAL_PERMISSION_CATEGORIES:
        for role in CANONICAL_MATRIX_ROLES:
            if (category, role, OLD_PERMISSION) in existing_category_rows:
                continue
            allowed = all(
                existing_category_rows.get((category, role, permission), False)
                for permission in NEW_PERMISSIONS
            )
            bind.execute(
                sa.insert(category_table).values(
                    category=category,
                    role=role,
                    permission=OLD_PERMISSION,
                    allowed=bool(allowed),
                )
            )
    bind.execute(sa.delete(category_table).where(category_table.c.permission.in_(NEW_PERMISSIONS)))
