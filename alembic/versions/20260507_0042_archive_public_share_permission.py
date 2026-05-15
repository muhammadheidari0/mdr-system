"""Add archive public share permission.

Revision ID: 20260507_0042
Revises: 20260507_0041
Create Date: 2026-05-07 03:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260507_0042"
down_revision = "20260507_0041"
branch_labels = None
depends_on = None

PERMISSION = "archive:share"
ALL_ROLES = ("admin", "manager", "dcc", "project_control", "user", "viewer")
DEFAULT_ROLES = {"admin", "manager", "dcc", "user"}
CATEGORIES = ("consultant", "contractor", "employer", "dcc")
MARKER_KEY = "migration.archive_public_share_permission.v1"


def _ensure_permission(bind, table, values: dict, *, allowed_default: bool) -> None:
    filters = [
        table.c.role == values["role"],
        table.c.permission == values["permission"],
    ]
    if "category" in values:
        filters.insert(0, table.c.category == values["category"])
    row = bind.execute(sa.select(table.c.allowed).where(*filters).limit(1)).first()
    if row:
        if allowed_default:
            bind.execute(sa.update(table).where(*filters).values(allowed=True))
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
    settings_table = sa.table(
        "settings_kv",
        sa.column("key", sa.String),
        sa.column("value", sa.Text),
        sa.column("updated_at", sa.DateTime),
    )

    for role in ALL_ROLES:
        allowed = role in DEFAULT_ROLES
        _ensure_permission(
            bind,
            role_table,
            {"role": role, "permission": PERMISSION, "allowed": allowed},
            allowed_default=allowed,
        )

    for category in CATEGORIES:
        for role in ALL_ROLES:
            allowed = role in DEFAULT_ROLES
            _ensure_permission(
                bind,
                category_table,
                {
                    "category": category,
                    "role": role,
                    "permission": PERMISSION,
                    "allowed": allowed,
                },
                allowed_default=allowed,
            )

    marker_exists = bind.execute(
        sa.select(settings_table.c.key).where(settings_table.c.key == MARKER_KEY).limit(1)
    ).first()
    if not marker_exists:
        bind.execute(sa.insert(settings_table).values(key=MARKER_KEY, value="1", updated_at=sa.func.now()))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_category_permissions WHERE permission = :permission"), {"permission": PERMISSION})
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission = :permission"), {"permission": PERMISSION})
    bind.execute(sa.text("DELETE FROM settings_kv WHERE key = :key"), {"key": MARKER_KEY})
