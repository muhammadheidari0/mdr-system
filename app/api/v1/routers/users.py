from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import get_db, require_permission
from app.core.organizations import ALL_ORG_TYPES, OrganizationRole, OrganizationType, normalize_org_role, normalize_org_type
from app.db.models import Organization, User, UserDisciplineScope, UserProjectScope
from app.core.security import get_password_hash
from app.schemas.auth import UserResponse, UserCreate, UserUpdate, UserListResponse
from app.services.access_control import resolve_effective_access, sync_legacy_role_from_access

router = APIRouter(prefix="/users", tags=["Users"])


def _normalize_text(value: Optional[str]) -> str:
    return str(value or "").strip()


def _base_users_query(
    db: Session,
    *,
    search: Optional[str] = None,
    role: Optional[str] = None,
    organization_id: Optional[int] = None,
    organization_type: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    q = db.query(User).options(joinedload(User.organization))
    search_value = _normalize_text(search)
    if search_value:
        pattern = f"%{search_value}%"
        q = q.filter(
            or_(
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
            )
        )

    role_value = _normalize_text(role).lower()
    if role_value:
        if role_value not in {"admin", "manager", "dcc", "user", "viewer"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role filter: {role_value}",
            )
        if role_value == OrganizationRole.ADMIN.value:
            q = q.filter(
                or_(
                    User.role == OrganizationRole.ADMIN.value,
                    User.organization.has(Organization.org_type == OrganizationType.SYSTEM.value),
                )
            )
        else:
            q = q.filter(
                or_(
                    and_(
                        User.organization_id.isnot(None),
                        User.organization.has(Organization.org_type != OrganizationType.SYSTEM.value),
                        User.organization_role == role_value,
                    ),
                    and_(
                        User.organization_id.is_(None),
                        User.role == role_value,
                    ),
                )
            )

    if organization_id is not None:
        q = q.filter(User.organization_id == int(organization_id))

    organization_type_value = normalize_org_type(organization_type)
    if organization_type_value:
        if organization_type_value not in ALL_ORG_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid organization_type: {organization_type_value}",
            )
        q = q.join(Organization, User.organization_id == Organization.id).filter(
            Organization.org_type == organization_type_value
        )

    if is_active is not None:
        q = q.filter(User.is_active == is_active)
    return q


def _validate_organization_or_400(
    db: Session,
    organization_id: Optional[int],
) -> Optional[Organization]:
    if organization_id is None:
        return None
    org = db.query(Organization).filter(Organization.id == int(organization_id)).first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization not found: {organization_id}",
        )
    return org


def _default_organization(db: Session) -> Optional[Organization]:
    root = db.query(Organization).filter(Organization.code == "SYSTEM_ROOT").first()
    if root:
        return root
    return db.query(Organization).filter(Organization.is_active == True).order_by(Organization.id.asc()).first()


def _normalize_user_org_role_or_400(org: Optional[Organization], requested_role: Optional[str]) -> str:
    org_type = normalize_org_type(getattr(org, "org_type", None))
    role_value = normalize_org_role(requested_role) or OrganizationRole.VIEWER.value
    if org_type == OrganizationType.SYSTEM.value:
        return OrganizationRole.ADMIN.value
    if role_value == OrganizationRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_role=admin is only allowed for system organizations.",
        )
    if role_value not in {item.value for item in OrganizationRole if item.value != OrganizationRole.ADMIN.value}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid organization_role: {requested_role}",
        )
    return role_value


def _scope_counts_map(db: Session, user_ids: List[int]) -> Dict[int, dict]:
    if not user_ids:
        return {}

    project_counts = {
        int(row.user_id): int(row.count)
        for row in (
            db.query(
                UserProjectScope.user_id.label("user_id"),
                func.count(UserProjectScope.id).label("count"),
            )
            .filter(UserProjectScope.user_id.in_(user_ids))
            .group_by(UserProjectScope.user_id)
            .all()
        )
    }
    discipline_counts = {
        int(row.user_id): int(row.count)
        for row in (
            db.query(
                UserDisciplineScope.user_id.label("user_id"),
                func.count(UserDisciplineScope.id).label("count"),
            )
            .filter(UserDisciplineScope.user_id.in_(user_ids))
            .group_by(UserDisciplineScope.user_id)
            .all()
        )
    }

    result: Dict[int, dict] = {}
    for user_id in user_ids:
        projects_count = int(project_counts.get(user_id, 0))
        disciplines_count = int(discipline_counts.get(user_id, 0))
        has_custom_scope = (projects_count > 0 or disciplines_count > 0)
        result[int(user_id)] = {
            "projects_count": projects_count,
            "disciplines_count": disciplines_count,
            "has_custom_scope": has_custom_scope,
            "status": "restricted" if has_custom_scope else "full",
        }
    return result


def _serialize_user_with_scope(user: User, scope_map: Dict[int, dict]) -> dict:
    access = resolve_effective_access(user)
    scope_summary = scope_map.get(int(user.id), {
        "projects_count": 0,
        "disciplines_count": 0,
        "has_custom_scope": False,
        "status": "full",
    })
    if access.full_access:
        scope_summary = {
            "projects_count": 0,
            "disciplines_count": 0,
            "has_custom_scope": False,
            "status": "admin",
        }

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "organization_id": user.organization_id,
        "organization_role": user.organization_role,
        "effective_role": access.effective_role,
        "permission_category": access.permission_category,
        "is_system_admin": access.is_system_admin,
        "organization_type": access.organization_type,
        "organization": (
            {
                "id": user.organization.id,
                "code": user.organization.code,
                "name": user.organization.name,
                "org_type": user.organization.org_type,
                "parent_id": user.organization.parent_id,
            }
            if user.organization
            else None
        ),
        "is_active": user.is_active,
        "created_at": user.created_at,
        "scope_summary": scope_summary,
    }


@router.get("/", response_model=List[UserResponse])
def list_users(
    skip: int = 0,
    limit: int = 100,
    q: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    organization_id: Optional[int] = Query(default=None),
    organization_type: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:read"))
):
    """
    لیست تمام کاربران (فقط ادمین)
    """
    users = (
        _base_users_query(
            db,
            search=q,
            role=role,
            organization_id=organization_id,
            organization_type=organization_type,
            is_active=is_active,
        )
        .order_by(User.created_at.desc(), User.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    scope_map = _scope_counts_map(db, [int(u.id) for u in users])
    return [_serialize_user_with_scope(user, scope_map) for user in users]


@router.get("/paged", response_model=UserListResponse)
def list_users_paged(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    q: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    organization_id: Optional[int] = Query(default=None),
    organization_type: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:read")),
):
    """
    لیست صفحه‌بندی‌شده کاربران با قابلیت جستجو و فیلتر (فقط ادمین)
    """
    base_query = _base_users_query(
        db,
        search=q,
        role=role,
        organization_id=organization_id,
        organization_type=organization_type,
        is_active=is_active,
    )
    total = base_query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    effective_page = min(page, total_pages) if total else 1
    offset = (effective_page - 1) * page_size

    items = (
        base_query
        .order_by(User.created_at.desc(), User.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    scope_map = _scope_counts_map(db, [int(u.id) for u in items])
    serialized_items = [_serialize_user_with_scope(user, scope_map) for user in items]

    return {
        "ok": True,
        "items": serialized_items,
        "pagination": {
            "total": total,
            "page": effective_page,
            "page_size": page_size,
            "total_pages": total_pages,
            "count": len(serialized_items),
            "has_prev": effective_page > 1,
            "has_next": effective_page < total_pages,
        },
    }

@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:create"))
):
    """
    ایجاد کاربر جدید (فقط ادمین)
    """
    # بررسی تکراری نبودن ایمیل
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ایمیل قبلاً ثبت شده است"
        )
    
    org = _validate_organization_or_400(db, user.organization_id) if user.organization_id is not None else _default_organization(db)

    # هش کردن رمز عبور
    try:
        hashed_password = get_password_hash(user.password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    
    # ایجاد کاربر جدید
    organization_role = _normalize_user_org_role_or_400(org, user.organization_role.value)
    db_user = User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        role=user.role.value,  # legacy input; synchronized below from effective role
        organization_id=(org.id if org else None),
        organization_role=organization_role,
        is_active=user.is_active
    )
    sync_legacy_role_from_access(db_user)
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    db_user = (
        db.query(User)
        .options(joinedload(User.organization))
        .filter(User.id == db_user.id)
        .first()
    )
    scope_map = _scope_counts_map(db, [int(db_user.id)])
    return _serialize_user_with_scope(db_user, scope_map)

@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:read"))
):
    """
    دریافت اطلاعات کاربر مشخص (فقط ادمین)
    """
    user = (
        db.query(User)
        .options(joinedload(User.organization))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="کاربر یافت نشد"
        )
    scope_map = _scope_counts_map(db, [int(user.id)])
    return _serialize_user_with_scope(user, scope_map)

@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:update"))
):
    """
    ویرایش اطلاعات کاربر (فقط ادمین)
    """
    user = (
        db.query(User)
        .options(joinedload(User.organization))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="کاربر یافت نشد"
        )
    
    # آپدیت فیلدها
    if user_update.full_name is not None:
        user.full_name = user_update.full_name
    if user_update.role is not None:
        user.role = user_update.role.value
    if user_update.organization_id is not None:
        org = _validate_organization_or_400(db, user_update.organization_id)
        user.organization_id = org.id if org else None
    else:
        org = user.organization
    if user_update.organization_role is not None:
        user.organization_role = _normalize_user_org_role_or_400(org, user_update.organization_role.value)
    else:
        user.organization_role = _normalize_user_org_role_or_400(org, user.organization_role)
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
    sync_legacy_role_from_access(user)
    
    db.commit()
    db.refresh(user)
    user = (
        db.query(User)
        .options(joinedload(User.organization))
        .filter(User.id == user_id)
        .first()
    )
    scope_map = _scope_counts_map(db, [int(user.id)])
    return _serialize_user_with_scope(user, scope_map)

@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:delete"))
):
    """
    حذف کاربر (فقط ادمین)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="کاربر یافت نشد"
        )
    
    # جلوگیری از حذف خود ادمین
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="امکان حذف حساب کاربری خود وجود ندارد"
        )
    
    db.delete(user)
    db.commit()
    
    return {"message": "کاربر با موفقیت حذف شد"}


@router.get("/organizations/catalog")
def list_organizations_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("organizations:read")),
):
    rows = (
        db.query(Organization)
        .order_by(Organization.parent_id.is_(None).desc(), Organization.parent_id.asc(), Organization.name.asc())
        .all()
    )
    return {
        "ok": True,
        "items": [
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "org_type": row.org_type,
                "parent_id": row.parent_id,
                "is_active": bool(row.is_active),
            }
            for row in rows
        ],
    }
