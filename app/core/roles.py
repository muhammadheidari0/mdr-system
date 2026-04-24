from enum import Enum
from typing import Dict, List


class Role(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    DCC = "dcc"
    VIEWER = "viewer"


ALL_ROLES: tuple[str, ...] = tuple(role.value for role in Role)
MATRIX_ROLES: tuple[str, ...] = (
    Role.MANAGER.value,
    Role.DCC.value,
    Role.USER.value,
    Role.VIEWER.value,
)
EFFECTIVE_ROLES: tuple[str, ...] = (
    Role.ADMIN.value,
    *MATRIX_ROLES,
)


COMMON_NAV_PERMISSIONS: List[str] = [
    "dashboard:read",
    "reports:read",
    "module_settings:read",
    "hub_edms:read",
    "hub_reports:read",
    "hub_contractor:read",
    "hub_consultant:read",
    "module_archive:read",
    "module_transmittal:read",
    "module_correspondence:read",
    "module_reports:read",
    "module_site_logs_contractor:read",
    "module_comm_items_contractor:read",
    "module_permit_qc_contractor:read",
    "module_site_logs_consultant:read",
    "module_comm_items_consultant:read",
    "module_permit_qc_consultant:read",
]

WORKBOARD_PERMISSIONS: List[str] = [
    "workboard:read",
    "workboard:create",
    "workboard:update",
    "workboard:delete",
]

SITE_LOGS_READ_PERMISSIONS: List[str] = [
    "site_logs:read",
    "site_logs:report_read",
]

SITE_LOGS_WRITE_PERMISSIONS: List[str] = [
    "site_logs:create",
    "site_logs:update",
    "site_logs:submit",
    "site_logs:verify",
    "site_logs:comment_create",
    "site_logs:attachment_upload",
    "site_logs:attachment_delete",
]

COMM_ITEMS_READ_PERMISSIONS: List[str] = [
    "comm_items:read",
    "comm_items:report_read",
]

COMM_ITEMS_WRITE_PERMISSIONS: List[str] = [
    "comm_items:create",
    "comm_items:update",
    "comm_items:transition",
    "comm_items:comment_create",
    "comm_items:attachment_upload",
    "comm_items:attachment_delete",
    "comm_items:relation_manage",
]

DOCUMENT_WRITE_PERMISSIONS: List[str] = [
    "documents:delete",
    "documents:comment_create",
    "documents:comment_update",
    "documents:comment_delete",
    "documents:relation_manage",
    "documents:tag_manage",
]

BIM_READ_PERMISSIONS: List[str] = [
    "bim:read",
]

BIM_WRITE_PERMISSIONS: List[str] = [
    "bim:publish",
    "bim:approve",
    "bim:reject",
    "bim:schedule_ingest",
    "bim:schedule_approve",
    "bim:schedule_reject",
    "bim:site_logs_sync",
]


# Default RBAC matrix baseline.
ROLE_PERMISSIONS: Dict[Role, List[str]] = {
    Role.ADMIN: ["*"],
    Role.MANAGER: [
        "documents:read",
        "documents:create",
        "documents:update",
        *DOCUMENT_WRITE_PERMISSIONS,
        "archive:read",
        "archive:update",
        "transmittal:read",
        "transmittal:create",
        "transmittal:update",
        "correspondence:read",
        "correspondence:create",
        "correspondence:update",
        "correspondence:delete",
        "permit_qc:read",
        "permit_qc:create",
        "permit_qc:update",
        "permit_qc:submit",
        "permit_qc:review",
        "permit_qc:template_manage",
        "permit_qc:attachment_upload",
        "permit_qc:attachment_delete",
        *COMMON_NAV_PERMISSIONS,
        *WORKBOARD_PERMISSIONS,
        *SITE_LOGS_READ_PERMISSIONS,
        *SITE_LOGS_WRITE_PERMISSIONS,
        *COMM_ITEMS_READ_PERMISSIONS,
        *COMM_ITEMS_WRITE_PERMISSIONS,
        *BIM_READ_PERMISSIONS,
        *BIM_WRITE_PERMISSIONS,
    ],
    Role.DCC: [
        "documents:read",
        "documents:create",
        "documents:update",
        *DOCUMENT_WRITE_PERMISSIONS,
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
        "permit_qc:read",
        "permit_qc:create",
        "permit_qc:update",
        "permit_qc:submit",
        "permit_qc:review",
        "permit_qc:template_manage",
        "permit_qc:attachment_upload",
        "permit_qc:attachment_delete",
        *COMMON_NAV_PERMISSIONS,
        *WORKBOARD_PERMISSIONS,
        *SITE_LOGS_READ_PERMISSIONS,
        *SITE_LOGS_WRITE_PERMISSIONS,
        *COMM_ITEMS_READ_PERMISSIONS,
        *COMM_ITEMS_WRITE_PERMISSIONS,
        *BIM_READ_PERMISSIONS,
        *BIM_WRITE_PERMISSIONS,
    ],
    Role.USER: [
        "documents:read",
        "documents:create",
        "documents:update",
        "documents:comment_create",
        "documents:comment_update",
        "documents:comment_delete",
        "documents:relation_manage",
        "documents:tag_manage",
        "archive:read",
        "archive:update",
        "transmittal:read",
        "transmittal:create",
        "correspondence:read",
        "correspondence:create",
        "correspondence:update",
        "correspondence:delete",
        "permit_qc:read",
        "permit_qc:create",
        "permit_qc:update",
        "permit_qc:submit",
        "permit_qc:review",
        "permit_qc:attachment_upload",
        "permit_qc:attachment_delete",
        *COMMON_NAV_PERMISSIONS,
        *WORKBOARD_PERMISSIONS,
        *SITE_LOGS_READ_PERMISSIONS,
        *SITE_LOGS_WRITE_PERMISSIONS,
        *COMM_ITEMS_READ_PERMISSIONS,
        *COMM_ITEMS_WRITE_PERMISSIONS,
        *BIM_READ_PERMISSIONS,
        "bim:publish",
        "bim:schedule_ingest",
        "bim:site_logs_sync",
    ],
    Role.VIEWER: [
        "documents:read",
        "archive:read",
        "transmittal:read",
        "correspondence:read",
        "permit_qc:read",
        *COMMON_NAV_PERMISSIONS,
        "workboard:read",
        "site_logs:read",
        "site_logs:report_read",
        "comm_items:read",
        "comm_items:report_read",
        *BIM_READ_PERMISSIONS,
    ],
}


def normalize_role(user_role: str | None) -> str:
    return (user_role or "").strip().lower()


def is_valid_role(user_role: str | None) -> bool:
    return normalize_role(user_role) in EFFECTIVE_ROLES


def verify_role_access(user_role: str, required_roles: List[str]) -> bool:
    """Check whether user role is one of allowed roles."""
    normalized_user_role = normalize_role(user_role)
    normalized_required_roles = [normalize_role(role) for role in required_roles]
    if normalized_user_role == Role.ADMIN.value:
        return True
    return normalized_user_role in normalized_required_roles
