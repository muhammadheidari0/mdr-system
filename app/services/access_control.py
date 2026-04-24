from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.organizations import (
    DEFAULT_PERMISSION_CATEGORY,
    OrganizationType,
    normalize_org_role,
    normalize_org_type,
    normalize_permission_category,
)
from app.core.roles import MATRIX_ROLES, Role, normalize_role


@dataclass(frozen=True)
class EffectiveAccess:
    effective_role: str
    permission_category: str
    organization_type: str
    is_system_admin: bool
    full_access: bool


def _legacy_role_fallback(user: Any) -> str:
    role = normalize_role(getattr(user, "role", None))
    if role in MATRIX_ROLES:
        return role
    return Role.VIEWER.value


def resolve_effective_access(user: Any) -> EffectiveAccess:
    organization = getattr(user, "organization", None)
    organization_type = normalize_org_type(getattr(organization, "org_type", None))

    # Backward-compatible bootstrap: legacy admin without an organization must
    # still be able to administer the system until the data migration assigns it.
    legacy_role = normalize_role(getattr(user, "role", None))
    if not organization_type and legacy_role == Role.ADMIN.value:
        organization_type = OrganizationType.SYSTEM.value

    if organization_type == OrganizationType.SYSTEM.value:
        return EffectiveAccess(
            effective_role=Role.ADMIN.value,
            permission_category=OrganizationType.SYSTEM.value,
            organization_type=OrganizationType.SYSTEM.value,
            is_system_admin=True,
            full_access=True,
        )

    organization_role = normalize_org_role(getattr(user, "organization_role", None))
    if organization_role == Role.ADMIN.value:
        organization_role = Role.MANAGER.value
    if organization_role not in MATRIX_ROLES:
        organization_role = _legacy_role_fallback(user)

    category = normalize_permission_category(organization_type or None)
    if category == OrganizationType.SYSTEM.value:
        category = DEFAULT_PERMISSION_CATEGORY

    return EffectiveAccess(
        effective_role=organization_role,
        permission_category=category,
        organization_type=organization_type or "",
        is_system_admin=False,
        full_access=False,
    )


def sync_legacy_role_from_access(user: Any) -> None:
    access = resolve_effective_access(user)
    try:
        user.role = access.effective_role
    except Exception:
        return
