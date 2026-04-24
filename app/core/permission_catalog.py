from __future__ import annotations

from app.core.roles import ROLE_PERMISSIONS


SYSTEM_PERMISSION_KEYS: tuple[str, ...] = (
    "settings:read",
    "settings:update",
    "permissions:read",
    "permissions:update",
    "permissions:audit_read",
    "users:read",
    "users:create",
    "users:update",
    "users:delete",
    "organizations:read",
    "organizations:manage",
    "lookup:read",
    "lookup:manage",
    "storage:read",
    "storage:update",
    "storage:sync_manage",
    "site_cache:read",
    "site_cache:manage",
    "integrations:read",
    "integrations:update",
)


def permission_keys() -> list[str]:
    keys: set[str] = set(SYSTEM_PERMISSION_KEYS)
    for permissions in ROLE_PERMISSIONS.values():
        for permission in permissions or []:
            if permission and permission != "*":
                keys.add(str(permission))
    return sorted(keys)
