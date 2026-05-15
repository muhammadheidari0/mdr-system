"""Add meeting minutes and resolutions module.

Revision ID: 20260505_0038
Revises: 20260505_0037
Create Date: 2026-05-05 19:45:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260505_0038"
down_revision = "20260505_0037"
branch_labels = None
depends_on = None


PERMISSIONS = (
    "module_meeting_minutes:read",
    "meeting_minutes:read",
    "meeting_minutes:create",
    "meeting_minutes:update",
    "meeting_minutes:delete",
    "meeting_minutes:attachment",
)
ALL_ROLES = ("admin", "manager", "dcc", "project_control", "user", "viewer")
WRITE_ROLES = {"admin", "manager", "dcc", "user"}
READ_ROLES = {"admin", "manager", "dcc", "project_control", "user", "viewer"}
CATEGORIES = ("consultant", "contractor", "employer", "dcc")
MARKER_KEY = "migration.meeting_minutes.v1"


def _permission_allowed(role: str, permission: str) -> bool:
    if role == "admin":
        return True
    if permission in {"module_meeting_minutes:read", "meeting_minutes:read"}:
        return role in READ_ROLES
    if permission in {"meeting_minutes:create", "meeting_minutes:update", "meeting_minutes:attachment"}:
        return role in WRITE_ROLES or role == "project_control"
    return role in WRITE_ROLES


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
    op.create_table(
        "meeting_minutes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("meeting_no", sa.String(length=120), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=True),
        sa.Column("meeting_type", sa.String(length=64), nullable=False, server_default="General"),
        sa.Column("meeting_date", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("chairperson", sa.String(length=255), nullable=True),
        sa.Column("secretary", sa.String(length=255), nullable=True),
        sa.Column("participants", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="Open"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_meeting_minutes_project_date", "meeting_minutes", ["project_code", "meeting_date"])
    op.create_index("ix_meeting_minutes_meeting_no", "meeting_minutes", ["meeting_no"])
    op.create_index("ix_meeting_minutes_status", "meeting_minutes", ["status"])
    op.create_index("ix_meeting_minutes_deleted_at", "meeting_minutes", ["deleted_at"])

    op.create_table(
        "meeting_resolutions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("meeting_minute_id", sa.Integer(), nullable=False),
        sa.Column("resolution_no", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("responsible_user_id", sa.Integer(), nullable=True),
        sa.Column("responsible_org_id", sa.Integer(), nullable=True),
        sa.Column("responsible_name", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="Open"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="Normal"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["meeting_minute_id"], ["meeting_minutes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["responsible_org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_meeting_resolutions_minute", "meeting_resolutions", ["meeting_minute_id"])
    op.create_index("ix_meeting_resolutions_status_due", "meeting_resolutions", ["status", "due_date"])
    op.create_index("ix_meeting_resolutions_responsible_user", "meeting_resolutions", ["responsible_user_id"])
    op.create_index("ix_meeting_resolutions_deleted_at", "meeting_resolutions", ["deleted_at"])

    op.create_table(
        "meeting_minute_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("meeting_minute_id", sa.Integer(), nullable=False),
        sa.Column("resolution_id", sa.Integer(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=1024), nullable=False),
        sa.Column("file_kind", sa.String(length=20), nullable=False, server_default="attachment"),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("detected_mime", sa.String(length=128), nullable=True),
        sa.Column("validation_status", sa.String(length=32), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_backend", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("mirror_provider", sa.String(length=32), nullable=True),
        sa.Column("mirror_remote_id", sa.String(length=255), nullable=True),
        sa.Column("mirror_remote_url", sa.String(length=1024), nullable=True),
        sa.Column("mirror_status", sa.String(length=32), nullable=True),
        sa.Column("mirror_updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["meeting_minute_id"], ["meeting_minutes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolution_id"], ["meeting_resolutions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_meeting_minute_attachments_minute", "meeting_minute_attachments", ["meeting_minute_id"])
    op.create_index("ix_meeting_minute_attachments_resolution", "meeting_minute_attachments", ["resolution_id"])
    op.create_index("ix_meeting_minute_attachments_uploaded_at", "meeting_minute_attachments", ["uploaded_at"])
    op.create_index("ix_meeting_minute_attachments_deleted_at", "meeting_minute_attachments", ["deleted_at"])

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
        for permission in PERMISSIONS:
            allowed = _permission_allowed(role, permission)
            _ensure_permission(
                bind,
                role_table,
                {"role": role, "permission": permission, "allowed": allowed},
                allowed_default=allowed,
            )

    for category in CATEGORIES:
        for role in ALL_ROLES:
            for permission in PERMISSIONS:
                allowed = _permission_allowed(role, permission)
                if category != "dcc" and permission == "module_meeting_minutes:read":
                    allowed = False
                _ensure_permission(
                    bind,
                    category_table,
                    {
                        "category": category,
                        "role": role,
                        "permission": permission,
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
    delete_category = sa.text(
        "DELETE FROM role_category_permissions WHERE permission IN :permissions"
    ).bindparams(sa.bindparam("permissions", expanding=True))
    delete_role = sa.text(
        "DELETE FROM role_permissions WHERE permission IN :permissions"
    ).bindparams(sa.bindparam("permissions", expanding=True))
    bind.execute(delete_category, {"permissions": list(PERMISSIONS)})
    bind.execute(delete_role, {"permissions": list(PERMISSIONS)})
    bind.execute(sa.text("DELETE FROM settings_kv WHERE key = :key"), {"key": MARKER_KEY})

    op.drop_index("ix_meeting_minute_attachments_deleted_at", table_name="meeting_minute_attachments")
    op.drop_index("ix_meeting_minute_attachments_uploaded_at", table_name="meeting_minute_attachments")
    op.drop_index("ix_meeting_minute_attachments_resolution", table_name="meeting_minute_attachments")
    op.drop_index("ix_meeting_minute_attachments_minute", table_name="meeting_minute_attachments")
    op.drop_table("meeting_minute_attachments")

    op.drop_index("ix_meeting_resolutions_deleted_at", table_name="meeting_resolutions")
    op.drop_index("ix_meeting_resolutions_responsible_user", table_name="meeting_resolutions")
    op.drop_index("ix_meeting_resolutions_status_due", table_name="meeting_resolutions")
    op.drop_index("ix_meeting_resolutions_minute", table_name="meeting_resolutions")
    op.drop_table("meeting_resolutions")

    op.drop_index("ix_meeting_minutes_deleted_at", table_name="meeting_minutes")
    op.drop_index("ix_meeting_minutes_status", table_name="meeting_minutes")
    op.drop_index("ix_meeting_minutes_meeting_no", table_name="meeting_minutes")
    op.drop_index("ix_meeting_minutes_project_date", table_name="meeting_minutes")
    op.drop_table("meeting_minutes")
