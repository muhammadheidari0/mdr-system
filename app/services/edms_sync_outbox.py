from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.core.organizations import PERMISSION_CATEGORIES
from app.core.roles import ROLE_PERMISSIONS
from app.db.models import (
    Block,
    Discipline,
    DocStatus,
    IssuingEntity,
    Level,
    MdrCategory,
    Organization,
    Package,
    Phase,
    Project,
    RoleCategoryDisciplineScope,
    RoleCategoryPermission,
    RoleCategoryProjectScope,
    User,
    UserDisciplineScope,
    UserProjectScope,
)
from app.services.edms_event_signing import build_signed_event


EVENT_ENDPOINTS: dict[str, str] = {
    "projects": "/apps/edms/api/sync/projects",
    "catalogs": "/apps/edms/api/sync/catalogs",
    "organizations": "/apps/edms/api/sync/organizations",
    "users": "/apps/edms/api/sync/users",
    "permissions": "/apps/edms/api/sync/permissions",
    "scopes": "/apps/edms/api/sync/scopes",
}


def _permission_catalog() -> list[str]:
    keys: set[str] = set()
    for permissions in ROLE_PERMISSIONS.values():
        for permission in permissions or []:
            if permission and permission != "*":
                keys.add(str(permission))
    return sorted(keys)


def build_master_data_snapshot(db: Session) -> dict[str, Any]:
    projects = [
        {
            "code": row.code,
            "name_e": row.name_e or "",
            "name_p": row.name_p or "",
            "is_active": bool(row.is_active),
        }
        for row in db.query(Project).order_by(Project.code.asc()).all()
    ]
    blocks = [
        {
            "project_code": row.project_code,
            "code": row.code,
            "name_e": row.name_e or "",
            "name_p": row.name_p or "",
            "is_active": bool(row.is_active),
            "sort_order": int(row.sort_order or 0),
        }
        for row in db.query(Block).order_by(Block.project_code.asc(), Block.code.asc()).all()
    ]
    disciplines = [
        {"code": row.code, "name_e": row.name_e or "", "name_p": row.name_p or ""}
        for row in db.query(Discipline).order_by(Discipline.code.asc()).all()
    ]
    packages = [
        {
            "discipline_code": row.discipline_code,
            "package_code": row.package_code,
            "name_e": row.name_e or "",
            "name_p": row.name_p or "",
        }
        for row in db.query(Package).order_by(Package.discipline_code.asc(), Package.package_code.asc()).all()
    ]
    levels = [
        {
            "code": row.code,
            "name_e": row.name_e or "",
            "name_p": row.name_p or "",
            "sort_order": int(row.sort_order or 0),
        }
        for row in db.query(Level).order_by(Level.sort_order.asc(), Level.code.asc()).all()
    ]
    phases = [
        {"ph_code": row.ph_code, "name_e": row.name_e or "", "name_p": row.name_p or ""}
        for row in db.query(Phase).order_by(Phase.ph_code.asc()).all()
    ]
    mdr_categories = [
        {
            "code": row.code,
            "name_e": row.name_e or "",
            "name_p": row.name_p or "",
            "folder_name": row.folder_name or "",
            "is_active": bool(row.is_active),
            "sort_order": int(row.sort_order or 0),
        }
        for row in db.query(MdrCategory).order_by(MdrCategory.sort_order.asc(), MdrCategory.code.asc()).all()
    ]
    doc_statuses = [
        {
            "code": row.code,
            "name": row.name or "",
            "description": row.description or "",
            "sort_order": int(row.sort_order or 0),
        }
        for row in db.query(DocStatus).order_by(DocStatus.sort_order.asc(), DocStatus.code.asc()).all()
    ]
    issuing_entities = [
        {
            "code": row.code,
            "name_e": row.name_e or "",
            "name_p": row.name_p or "",
            "project_code": row.project_code or "",
            "is_active": bool(row.is_active),
            "sort_order": int(row.sort_order or 0),
        }
        for row in db.query(IssuingEntity).order_by(IssuingEntity.sort_order.asc(), IssuingEntity.code.asc()).all()
    ]
    organizations = [
        {
            "id": int(row.id),
            "code": row.code,
            "name": row.name,
            "org_type": row.org_type,
            "parent_id": int(row.parent_id or 0) or None,
            "is_active": bool(row.is_active),
        }
        for row in db.query(Organization).order_by(Organization.id.asc()).all()
    ]
    users = [
        {
            "id": int(row.id),
            "email": row.email,
            "full_name": row.full_name or "",
            "role": row.role,
            "organization_id": int(row.organization_id or 0) or None,
            "organization_code": row.organization.code if row.organization else None,
            "organization_type": row.organization.org_type if row.organization else None,
            "organization_role": row.organization_role,
            "is_active": bool(row.is_active),
        }
        for row in db.query(User).options(joinedload(User.organization)).order_by(User.id.asc()).all()
    ]
    role_category_permissions = [
        {
            "category": row.category,
            "role": row.role,
            "permission": row.permission,
            "allowed": bool(row.allowed),
        }
        for row in db.query(RoleCategoryPermission).order_by(
            RoleCategoryPermission.category.asc(),
            RoleCategoryPermission.role.asc(),
            RoleCategoryPermission.permission.asc(),
        ).all()
    ]
    role_category_project_scopes = [
        {
            "category": row.category,
            "role": row.role,
            "project_code": row.project_code,
        }
        for row in db.query(RoleCategoryProjectScope).order_by(
            RoleCategoryProjectScope.category.asc(),
            RoleCategoryProjectScope.role.asc(),
            RoleCategoryProjectScope.project_code.asc(),
        ).all()
    ]
    role_category_discipline_scopes = [
        {
            "category": row.category,
            "role": row.role,
            "discipline_code": row.discipline_code,
        }
        for row in db.query(RoleCategoryDisciplineScope).order_by(
            RoleCategoryDisciplineScope.category.asc(),
            RoleCategoryDisciplineScope.role.asc(),
            RoleCategoryDisciplineScope.discipline_code.asc(),
        ).all()
    ]
    user_project_scopes = [
        {
            "user_id": int(row.user_id),
            "project_code": row.project_code,
        }
        for row in db.query(UserProjectScope).order_by(UserProjectScope.user_id.asc(), UserProjectScope.project_code.asc()).all()
    ]
    user_discipline_scopes = [
        {
            "user_id": int(row.user_id),
            "discipline_code": row.discipline_code,
        }
        for row in db.query(UserDisciplineScope).order_by(
            UserDisciplineScope.user_id.asc(),
            UserDisciplineScope.discipline_code.asc(),
        ).all()
    ]
    return {
        "projects": projects,
        "blocks": blocks,
        "disciplines": disciplines,
        "packages": packages,
        "levels": levels,
        "phases": phases,
        "mdr_categories": mdr_categories,
        "doc_statuses": doc_statuses,
        "issuing_entities": issuing_entities,
        "organizations": organizations,
        "users": users,
        "role_category_permissions": role_category_permissions,
        "role_category_project_scopes": role_category_project_scopes,
        "role_category_discipline_scopes": role_category_discipline_scopes,
        "user_project_scopes": user_project_scopes,
        "user_discipline_scopes": user_discipline_scopes,
        "permission_catalog": _permission_catalog(),
        "permission_categories": list(PERMISSION_CATEGORIES),
    }


def build_sync_envelopes(db: Session, *, secret: str, source: str = "mdr_app") -> dict[str, dict[str, Any]]:
    snapshot = build_master_data_snapshot(db)
    payloads = {
        "projects": {
            "projects": snapshot["projects"],
            "blocks": snapshot["blocks"],
        },
        "catalogs": {
            "disciplines": snapshot["disciplines"],
            "packages": snapshot["packages"],
            "levels": snapshot["levels"],
            "phases": snapshot["phases"],
            "mdr_categories": snapshot["mdr_categories"],
            "doc_statuses": snapshot["doc_statuses"],
            "issuing_entities": snapshot["issuing_entities"],
        },
        "organizations": {
            "organizations": snapshot["organizations"],
        },
        "users": {
            "users": snapshot["users"],
        },
        "permissions": {
            "permission_catalog": snapshot["permission_catalog"],
            "permission_categories": snapshot["permission_categories"],
            "role_category_permissions": snapshot["role_category_permissions"],
        },
        "scopes": {
            "role_category_project_scopes": snapshot["role_category_project_scopes"],
            "role_category_discipline_scopes": snapshot["role_category_discipline_scopes"],
            "user_project_scopes": snapshot["user_project_scopes"],
            "user_discipline_scopes": snapshot["user_discipline_scopes"],
        },
    }
    return {
        key: build_signed_event(
            secret=secret,
            entity=key,
            operation="upsert",
            payload=value,
            source=source,
        )
        for key, value in payloads.items()
    }
