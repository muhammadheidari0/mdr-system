from __future__ import annotations
import json
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any, Dict, Generator, List
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from app.core.config import settings
from app.db.session import get_db as _get_db
from app.core.organizations import (
    is_contractor_category,
    normalize_permission_category,
)
from app.db.models import (
    Organization,
    RoleCategoryDisciplineScope,
    RoleCategoryPermission,
    RoleCategoryProjectScope,
    RoleDisciplineScope,
    RolePermission,
    RoleProjectScope,
    SettingsKV,
    User,
    UserDisciplineScope,
    UserProjectScope,
)
from app.core.security import verify_token
from app.core.roles import MATRIX_ROLES, ROLE_PERMISSIONS, Role, is_valid_role, normalize_role
from app.services.access_control import resolve_effective_access


def get_db() -> Generator[Session, None, None]:
    yield from _get_db()

security = HTTPBearer()
AUTH_SESSION_KEY_PREFIX = "auth.sess:"
AUTH_SESSION_TOUCH_THROTTLE_SECONDS = 120


def _utcnow() -> datetime:
    return datetime.utcnow()


def _session_key_for_token(token: str) -> str:
    digest = sha256(str(token or "").encode("utf-8")).hexdigest()[:48]
    return f"{AUTH_SESSION_KEY_PREFIX}{digest}"


def auth_idle_timeout_minutes() -> int:
    minutes = int(getattr(settings, "AUTH_IDLE_TIMEOUT_MINUTES", 20) or 0)
    return max(0, minutes)


def auth_heartbeat_interval_seconds() -> int:
    minutes = auth_idle_timeout_minutes()
    if minutes <= 0:
        return 0
    return max(60, min(300, int(minutes * 60 / 2)))


def _auth_idle_timeout() -> timedelta | None:
    minutes = auth_idle_timeout_minutes()
    if minutes <= 0:
        return None
    return timedelta(minutes=minutes)


def _parse_session_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _decode_session_value(value: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def revoke_auth_session(db: Session, token: str) -> None:
    if settings.READ_ONLY_MODE:
        return
    key = _session_key_for_token(token)
    row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    if not row:
        return
    db.delete(row)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()


def _is_user_activity_request(request: Request) -> bool:
    value = str(request.headers.get("x-user-activity") or "").strip().lower()
    return value in {"1", "true", "yes", "y"}


def _session_payload(user: User, now: datetime) -> str:
    return json.dumps(
        {"user_id": user.id, "email": user.email, "last_seen": now.isoformat(timespec="seconds")},
        ensure_ascii=False,
    )


def _commit_session_change(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()


def _should_touch_session(last_seen: datetime | None, now: datetime) -> bool:
    if last_seen is None:
        return True
    return now - last_seen >= timedelta(seconds=AUTH_SESSION_TOUCH_THROTTLE_SECONDS)


def _validate_auth_session(db: Session, user: User, token: str, *, touch: bool) -> None:
    timeout = _auth_idle_timeout()
    if timeout is None:
        return
    key = _session_key_for_token(token)
    now = _utcnow()
    row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    if row:
        payload = _decode_session_value(row.value)
        last_seen = _parse_session_timestamp(payload.get("last_seen"))
        if last_seen and now - last_seen > timeout:
            if not settings.READ_ONLY_MODE:
                db.delete(row)
                _commit_session_change(db)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired due to inactivity",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if touch and not settings.READ_ONLY_MODE and _should_touch_session(last_seen, now):
            row.value = _session_payload(user, now)
            row.updated_at = now
            _commit_session_change(db)
        return
    if not settings.READ_ONLY_MODE:
        db.add(
            SettingsKV(
                key=key,
                value=_session_payload(user, now),
                updated_at=now,
            )
        )
        _commit_session_change(db)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    email = verify_token(credentials.credentials)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = (
        db.query(User)
        .options(joinedload(User.organization))
        .filter(User.email == email)
        .first()
    )
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    _validate_auth_session(db, user, credentials.credentials, touch=_is_user_activity_request(request))
    return user

def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not resolve_effective_access(current_user).is_system_admin:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user

# Permission-based access control (matrix-driven)
def _fallback_permissions_for_role(role: str) -> set[str]:
    try:
        role_enum = Role(role)
    except Exception:
        return set()
    perms = set(ROLE_PERMISSIONS.get(role_enum, []) or [])
    return perms


def _load_allowed_permissions(
    db: Session,
    role: str,
    *,
    category: str | None = None,
) -> set[str]:
    category_key = normalize_permission_category(category) if category is not None else None
    if category_key == "system":
        return {"*"}
    if category_key:
        has_category_rows = (
            db.query(RoleCategoryPermission.id)
            .filter(
                RoleCategoryPermission.category == category_key,
                RoleCategoryPermission.role == role,
            )
            .first()
        )
        if has_category_rows:
            rows = (
                db.query(RoleCategoryPermission.permission)
                .filter(
                    RoleCategoryPermission.category == category_key,
                    RoleCategoryPermission.role == role,
                    RoleCategoryPermission.allowed == True,
                )
                .all()
            )
            return {str(perm or "").strip() for (perm,) in rows if str(perm or "").strip()}

    has_rows = db.query(RolePermission.role).filter(RolePermission.role == role).first()
    if has_rows:
        rows = (
            db.query(RolePermission.permission)
            .filter(RolePermission.role == role, RolePermission.allowed == True)
            .all()
        )
        return {str(perm or "").strip() for (perm,) in rows if str(perm or "").strip()}

    # Fallback to static defaults when matrix is not seeded.
    return _fallback_permissions_for_role(role)


def _has_permission(
    db: Session,
    role: str,
    permission: str,
    *,
    category: str | None = None,
) -> bool:
    allowed = _load_allowed_permissions(db, role, category=category)
    if "*" in allowed:
        return True
    return permission in allowed


class PermissionChecker:
    def __init__(self, permission: str):
        self.permission = str(permission or "").strip()

    def __call__(self, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        access = resolve_effective_access(user)
        user_role = access.effective_role
        user_category = access.permission_category
        if not is_valid_role(user_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unknown role: {user_role}",
            )
        if access.full_access:
            return user
        if not self.permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing permission requirement",
            )
        if not _has_permission(db, user_role, self.permission, category=user_category):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Missing permission: {self.permission}",
            )
        return user


def require_permission(permission: str) -> PermissionChecker:
    return PermissionChecker(permission)


def has_permission(db: Session, role: str, permission: str) -> bool:
    role_key = normalize_role(role)
    if not is_valid_role(role_key):
        return False
    if role_key == Role.ADMIN.value:
        return True
    if not str(permission or "").strip():
        return False
    return _has_permission(db, role_key, permission)


def has_permission_for_user(db: Session, user: User, permission: str) -> bool:
    access = resolve_effective_access(user)
    role_key = access.effective_role
    if not is_valid_role(role_key):
        return False
    if access.full_access:
        return True
    if not str(permission or "").strip():
        return False
    category = access.permission_category
    return _has_permission(db, role_key, permission, category=category)


def bulk_check_permissions_for_user(
    db: Session, user: User, permissions: list[str]
) -> dict[str, bool]:
    """Check multiple permissions in a single DB round-trip instead of one per permission."""
    access = resolve_effective_access(user)
    role_key = access.effective_role
    if not is_valid_role(role_key):
        return {perm: False for perm in permissions}
    if access.full_access:
        return {perm: True for perm in permissions}

    category = access.permission_category
    allowed = _load_allowed_permissions(db, role_key, category=category)

    if "*" in allowed:
        return {perm: True for perm in permissions}

    return {perm: perm in allowed for perm in permissions}


def _normalize_scope_values(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    for value in values:
        norm = str(value or "").strip().upper()
        if norm:
            normalized.append(norm)
    return sorted(set(normalized))


def _default_scope_rules() -> Dict[str, Dict[str, List[str]]]:
    return {
        role: {
            "projects": [],
            "disciplines": [],
        }
        for role in MATRIX_ROLES
    }


def _load_scope_rules(
    db: Session,
    *,
    category: str | None = None,
) -> Dict[str, Dict[str, List[str]]]:
    rules = _default_scope_rules()
    role_projects: List[tuple[str, str]] = []
    role_disciplines: List[tuple[str, str]] = []

    category_key = normalize_permission_category(category) if category is not None else None
    if category_key:
        has_category_context = (
            db.query(RoleCategoryPermission.id)
            .filter(RoleCategoryPermission.category == category_key)
            .first()
            is not None
        )
        if has_category_context:
            role_projects = (
                db.query(RoleCategoryProjectScope.role, RoleCategoryProjectScope.project_code)
                .filter(RoleCategoryProjectScope.category == category_key)
                .all()
            )
            role_disciplines = (
                db.query(RoleCategoryDisciplineScope.role, RoleCategoryDisciplineScope.discipline_code)
                .filter(RoleCategoryDisciplineScope.category == category_key)
                .all()
            )

    if not role_projects and not role_disciplines:
        role_projects = db.query(RoleProjectScope.role, RoleProjectScope.project_code).all()
        role_disciplines = db.query(
            RoleDisciplineScope.role, RoleDisciplineScope.discipline_code
        ).all()

    for role, project_code in role_projects:
        role_key = normalize_role(role)
        if role_key in rules:
            rules[role_key]["projects"].append(str(project_code or "").strip().upper())
    for role, discipline_code in role_disciplines:
        role_key = normalize_role(role)
        if role_key in rules:
            rules[role_key]["disciplines"].append(str(discipline_code or "").strip().upper())

    for role in MATRIX_ROLES:
        rules[role]["projects"] = sorted(set(rules[role]["projects"]))
        rules[role]["disciplines"] = sorted(set(rules[role]["disciplines"]))
    return rules


def _load_user_scope_rules(db: Session) -> Dict[str, Dict[str, List[str]]]:
    normalized: Dict[str, Dict[str, List[str]]] = {}
    for user_id, project_code in db.query(UserProjectScope.user_id, UserProjectScope.project_code).all():
        key = str(user_id)
        normalized.setdefault(key, {"projects": [], "disciplines": []})
        normalized[key]["projects"].append(str(project_code or "").strip().upper())
    for user_id, discipline_code in db.query(
        UserDisciplineScope.user_id, UserDisciplineScope.discipline_code
    ).all():
        key = str(user_id)
        normalized.setdefault(key, {"projects": [], "disciplines": []})
        normalized[key]["disciplines"].append(str(discipline_code or "").strip().upper())

    for key in list(normalized.keys()):
        normalized[key]["projects"] = sorted(set(normalized[key]["projects"]))
        normalized[key]["disciplines"] = sorted(set(normalized[key]["disciplines"]))
    return normalized


def _effective_scope_values(role_values: List[str], user_values: List[str]) -> tuple[List[str], bool]:
    role_set = set(role_values)
    user_set = set(user_values)
    if role_set and user_set:
        return sorted(role_set & user_set), True
    if role_set:
        return sorted(role_set), True
    if user_set:
        return sorted(user_set), True
    return [], False


def get_user_scope_filters(db: Session, user: User) -> Dict[str, Any]:
    access = resolve_effective_access(user)
    role = access.effective_role
    if access.full_access:
        return {
            "projects": [],
            "disciplines": [],
            "projects_restricted": False,
            "disciplines_restricted": False,
        }

    category = access.permission_category
    role_scope = _load_scope_rules(db, category=category).get(role, {})
    user_scope = _load_user_scope_rules(db).get(str(user.id), {})
    projects, projects_restricted = _effective_scope_values(
        _normalize_scope_values(role_scope.get("projects")),
        _normalize_scope_values(user_scope.get("projects")),
    )
    disciplines, disciplines_restricted = _effective_scope_values(
        _normalize_scope_values(role_scope.get("disciplines")),
        _normalize_scope_values(user_scope.get("disciplines")),
    )
    return {
        "projects": projects,
        "disciplines": disciplines,
        "projects_restricted": projects_restricted,
        "disciplines_restricted": disciplines_restricted,
    }


def enforce_scope_access(
    db: Session,
    user: User,
    *,
    project_code: str | None = None,
    discipline_code: str | None = None,
) -> None:
    if resolve_effective_access(user).full_access:
        return

    filters = get_user_scope_filters(db, user)
    project = str(project_code or "").strip().upper()
    discipline = str(discipline_code or "").strip().upper()

    if project and filters["projects_restricted"] and project not in filters["projects"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for project: {project}",
        )
    if discipline and filters["disciplines_restricted"] and discipline not in filters["disciplines"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for discipline: {discipline}",
        )


def apply_scope_query_filters(
    query,
    db: Session,
    user: User,
    *,
    project_column=None,
    discipline_column=None,
):
    if resolve_effective_access(user).full_access:
        return query

    filters = get_user_scope_filters(db, user)
    if project_column is not None and filters["projects_restricted"]:
        query = query.filter(project_column.in_(filters["projects"]))
    if discipline_column is not None and filters["disciplines_restricted"]:
        query = query.filter(discipline_column.in_(filters["disciplines"]))
    return query


def get_user_accessible_organization_ids(db: Session, user: User) -> List[int]:
    access = resolve_effective_access(user)
    if access.full_access:
        return []

    category = access.permission_category
    if not is_contractor_category(category):
        return []

    root_id = int(getattr(user, "organization_id", 0) or 0)
    if root_id <= 0:
        return [0]

    rows = db.query(Organization.id, Organization.parent_id).all()
    children_map: Dict[int, List[int]] = {}
    for org_id, parent_id in rows:
        if org_id is None:
            continue
        if parent_id is None:
            continue
        children_map.setdefault(int(parent_id), []).append(int(org_id))

    allowed = {root_id}
    queue = [root_id]
    while queue:
        current = queue.pop(0)
        for child_id in children_map.get(current, []):
            if child_id in allowed:
                continue
            allowed.add(child_id)
            queue.append(child_id)
    return sorted(allowed)


def apply_organization_query_filters(
    query,
    db: Session,
    user: User,
    *,
    organization_column=None,
):
    if organization_column is None:
        return query
    allowed_org_ids = get_user_accessible_organization_ids(db, user)
    if not allowed_org_ids:
        return query
    return query.filter(organization_column.in_(allowed_org_ids))


def enforce_organization_access(
    db: Session,
    user: User,
    *,
    organization_id: int | None,
) -> None:
    if resolve_effective_access(user).full_access:
        return

    allowed_org_ids = get_user_accessible_organization_ids(db, user)
    if not allowed_org_ids:
        return

    target_org_id = int(organization_id or 0)
    if target_org_id <= 0 or target_org_id not in allowed_org_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for organization scope",
        )
