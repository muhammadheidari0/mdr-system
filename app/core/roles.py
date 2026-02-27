from enum import Enum
from typing import Dict, List


class Role(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    DCC = "dcc"
    VIEWER = "viewer"


ALL_ROLES: tuple[str, ...] = tuple(role.value for role in Role)


# تعریف دسترسی‌های هر نقش (RBAC ثابت فاز 1)
ROLE_PERMISSIONS: Dict[Role, List[str]] = {
    Role.ADMIN: ["*"],  # دسترسی کامل
    Role.MANAGER: [
        "documents:read",
        "documents:create",
        "documents:update",
        "archive:read",
        "archive:update",
        "transmittal:read",
        "transmittal:create",
        "transmittal:update",
        "correspondence:read",
        "correspondence:create",
        "correspondence:update",
        "correspondence:delete",
        # By default, final issue/void remains with DCC.
        "dashboard:read",
        "module_settings:read",
    ],
    Role.DCC: [
        "documents:read",
        "documents:create",
        "documents:update",
        "archive:read",
        "archive:update",
        "transmittal:read",
        "transmittal:create",
        "transmittal:update",
        "transmittal:issue",
        "transmittal:void",
        "correspondence:read",
        "correspondence:create",
        "correspondence:update",
        "correspondence:delete",
        "dashboard:read",
        "module_settings:read",
    ],
    Role.USER: [
        "documents:read",
        "documents:create",
        "documents:update",
        "archive:read",
        "archive:update",
        "transmittal:read",
        "transmittal:create",
        "correspondence:read",
        "correspondence:create",
        "correspondence:update",
        "correspondence:delete",
        "dashboard:read",
        "module_settings:read",
    ],
    Role.VIEWER: [
        "documents:read",
        "archive:read",
        "transmittal:read",
        "correspondence:read",
        "dashboard:read",
        "module_settings:read",
    ],
}


def normalize_role(user_role: str | None) -> str:
    return (user_role or "").strip().lower()


def is_valid_role(user_role: str | None) -> bool:
    return normalize_role(user_role) in ALL_ROLES


def verify_role_access(user_role: str, required_roles: List[str]) -> bool:
    """بررسی می‌کند که آیا نقش کاربر در لیست نقش‌های مجاز هست یا خیر"""
    normalized_user_role = normalize_role(user_role)
    normalized_required_roles = [normalize_role(role) for role in required_roles]
    if normalized_user_role == Role.ADMIN.value:
        return True  # ادمین همیشه دسترسی دارد
    return normalized_user_role in normalized_required_roles
