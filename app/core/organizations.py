from enum import Enum
from typing import Any


class OrganizationType(str, Enum):
    SYSTEM = "system"
    EMPLOYER = "employer"
    CONSULTANT = "consultant"
    CONTRACTOR = "contractor"
    DCC = "dcc"


class OrganizationRole(str, Enum):
    ADMIN = "admin"
    DCC = "dcc"
    VIEWER = "viewer"


ALL_ORG_TYPES: tuple[str, ...] = tuple(item.value for item in OrganizationType)
ALL_ORG_ROLES: tuple[str, ...] = tuple(item.value for item in OrganizationRole)

PERMISSION_CATEGORIES: tuple[str, ...] = (
    OrganizationType.EMPLOYER.value,
    OrganizationType.CONSULTANT.value,
    OrganizationType.CONTRACTOR.value,
    OrganizationType.DCC.value,
    OrganizationType.SYSTEM.value,
)
DEFAULT_PERMISSION_CATEGORY = OrganizationType.CONSULTANT.value

ORG_TYPE_TO_PERMISSION_CATEGORY: dict[str, str] = {
    OrganizationType.SYSTEM.value: OrganizationType.SYSTEM.value,
    OrganizationType.EMPLOYER.value: OrganizationType.EMPLOYER.value,
    OrganizationType.CONSULTANT.value: OrganizationType.CONSULTANT.value,
    OrganizationType.CONTRACTOR.value: OrganizationType.CONTRACTOR.value,
    OrganizationType.DCC.value: OrganizationType.DCC.value,
}


def normalize_org_type(value: str | None) -> str:
    return str(value or "").strip().lower()


def normalize_org_role(value: str | None) -> str:
    return str(value or "").strip().lower()


def normalize_permission_category(value: str | None) -> str:
    key = normalize_org_type(value)
    mapped = ORG_TYPE_TO_PERMISSION_CATEGORY.get(key, key)
    if mapped not in PERMISSION_CATEGORIES:
        return DEFAULT_PERMISSION_CATEGORY
    return mapped


def resolve_user_permission_category(user: Any) -> str:
    organization = getattr(user, "organization", None)
    if organization is not None:
        return normalize_permission_category(getattr(organization, "org_type", None))
    role_key = str(getattr(user, "role", "") or "").strip().lower()
    if role_key == "admin":
        return OrganizationType.SYSTEM.value
    if role_key == "dcc":
        return OrganizationType.DCC.value
    return DEFAULT_PERMISSION_CATEGORY


def is_contractor_category(value: str | None) -> bool:
    return normalize_permission_category(value) == OrganizationType.CONTRACTOR.value
