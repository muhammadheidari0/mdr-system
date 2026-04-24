import json
from datetime import timedelta
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api import dependencies
from app.core import security
from app.core.organizations import OrganizationType
from app.core.roles import Role, normalize_role
from app.db import models
from app.schemas import auth as auth_schemas
from app.services.access_control import resolve_effective_access

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=auth_schemas.Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(dependencies.get_db)
):
    # لاگین با ایمیل (username در فرم دیتا)
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نام کاربری یا رمز عبور اشتباه است",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="حساب کاربری غیرفعال است"
        )
    
    access_token_expires = timedelta(minutes=30)
    access = resolve_effective_access(user)
    
    # ساخت توکن
    access_token = security.create_access_token(
        data={"sub": user.email, "role": access.effective_role},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=auth_schemas.UserResponse)
# اصلاح این خط: استفاده از dependencies.get_current_user به جای security.get_current_user
def read_users_me(current_user: models.User = Depends(dependencies.get_current_user)):
    access = resolve_effective_access(current_user)
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "organization_id": current_user.organization_id,
        "organization_role": current_user.organization_role,
        "effective_role": access.effective_role,
        "permission_category": access.permission_category,
        "is_system_admin": access.is_system_admin,
        "organization_type": access.organization_type,
        "organization": current_user.organization,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at,
    }


@router.get("/navigation")
def get_navigation(
    request: Request,
    db: Session = Depends(dependencies.get_db),
    current_user: models.User = Depends(dependencies.get_current_user),
):
    access = resolve_effective_access(current_user)
    user_role = access.effective_role
    category = access.permission_category

    # --- ETag caching: return 304 if permissions haven't changed ---
    etag_base = f"{user_role}:{category}:{getattr(current_user, 'organization_id', 0) or 0}"
    etag = f'W/"{sha256(etag_base.encode()).hexdigest()[:16]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    # --- Bulk permission check: single DB round-trip instead of 22 queries ---
    all_permissions = [
        "module_settings:read",
        "module_archive:read", "archive:read",
        "module_transmittal:read", "transmittal:read",
        "module_correspondence:read", "correspondence:read",
        "module_reports:read", "reports:read",
        "module_site_logs_contractor:read",
        "module_comm_items_contractor:read",
        "module_permit_qc_contractor:read",
        "module_site_logs_consultant:read",
        "module_comm_items_consultant:read",
        "module_permit_qc_consultant:read",
        "dashboard:read",
        "hub_edms:read",
        "hub_reports:read",
        "hub_contractor:read",
        "hub_consultant:read",
        "users:read",
        "users:create",
        "users:update",
        "users:delete",
        "organizations:read",
        "organizations:manage",
        "permissions:read",
        "permissions:update",
        "permissions:audit_read",
        "settings:read",
        "settings:update",
        "lookup:read",
        "lookup:manage",
        "storage:read",
        "storage:update",
        "storage:sync_manage",
        "site_cache:read",
        "site_cache:manage",
        "integrations:read",
        "integrations:update",
    ]
    p = dependencies.bulk_check_permissions_for_user(db, current_user, all_permissions)

    module_settings_allowed = p["module_settings:read"]

    modules = {
        "edms": {
            "archive": p["module_archive:read"] and p["archive:read"],
            "transmittal": p["module_transmittal:read"] and p["transmittal:read"],
            "correspondence": p["module_correspondence:read"] and p["correspondence:read"],
        },
        "reports": {
            "overview": p["module_reports:read"] and p["reports:read"],
        },
        "contractor": {
            "execution": p["module_site_logs_contractor:read"],
            "requests": p["module_comm_items_contractor:read"],
            "permit_qc": p["module_permit_qc_contractor:read"],
        },
        "consultant": {
            "inspection": p["module_site_logs_consultant:read"],
            "defects": p["module_comm_items_consultant:read"],
            "instructions": p["module_comm_items_consultant:read"],
            "control": p["module_comm_items_consultant:read"],
            "permit_qc": p["module_permit_qc_consultant:read"],
        },
        "settings": {
            "module_settings": module_settings_allowed,
        },
    }

    hubs = {
        "dashboard": p["dashboard:read"],
        "edms": p["hub_edms:read"] and any(bool(v) for v in modules["edms"].values()),
        "reports": p["hub_reports:read"] and bool(modules["reports"].get("overview")),
        "contractor": p["hub_contractor:read"] and any(bool(v) for v in modules["contractor"].values()),
        "consultant": p["hub_consultant:read"] and any(bool(v) for v in modules["consultant"].values()),
    }

    category_default_hub = {
        OrganizationType.DCC.value: "edms",
        OrganizationType.CONSULTANT.value: "consultant",
        OrganizationType.EMPLOYER.value: "reports",
        OrganizationType.CONTRACTOR.value: "contractor",
        OrganizationType.SYSTEM.value: "dashboard",
    }
    default_hub = category_default_hub.get(category, "dashboard")
    if not hubs.get(default_hub):
        default_hub = next((key for key in ("dashboard", "edms", "reports", "contractor", "consultant") if hubs.get(key)), "dashboard")

    tabs = {
        "archive": bool(modules["edms"]["archive"]),
        "transmittal": bool(modules["edms"]["transmittal"]),
        "correspondence": bool(modules["edms"]["correspondence"]),
        "reports": bool(modules["reports"]["overview"]),
    }

    role_default_map = {
        Role.ADMIN.value: "archive",
        Role.DCC.value: "transmittal",
        Role.MANAGER.value: "transmittal",
        Role.USER.value: "archive",
        Role.VIEWER.value: "archive",
    }
    default_tab = role_default_map.get(user_role, "archive")
    if not tabs.get(default_tab):
        default_tab = next((key for key in ("archive", "transmittal", "correspondence", "reports") if tabs.get(key)), "archive")

    response_data = {
        "ok": True,
        "category": category,
        "effective_role": access.effective_role,
        "permission_category": access.permission_category,
        "organization_type": access.organization_type,
        "is_system_admin": access.is_system_admin,
        "capabilities": p,
        "hubs": hubs,
        "default_hub": default_hub,
        "modules": modules,
        "edms_tabs": tabs,
        "default_edms_tab": default_tab,
        "module_settings": module_settings_allowed,
    }
    # Backward compatibility for legacy clients expecting per-hub module-settings flags.
    response_data["edms"] = module_settings_allowed
    response_data["contractor"] = module_settings_allowed
    response_data["consultant"] = module_settings_allowed

    return Response(
        content=json.dumps(response_data),
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "private, max-age=300"},
    )


@router.post("/change-password")
def change_password(
    password_data: auth_schemas.PasswordChangeRequest,
    db: Session = Depends(dependencies.get_db),
    current_user: models.User = Depends(dependencies.get_current_user),
):
    if not security.verify_password(
        password_data.current_password, current_user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="رمز عبور فعلی اشتباه است",
        )

    if password_data.current_password == password_data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="رمز جدید باید با رمز فعلی متفاوت باشد",
        )

    try:
        current_user.hashed_password = security.get_password_hash(
            password_data.new_password
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    db.commit()

    return {"ok": True, "message": "رمز عبور با موفقیت تغییر کرد"}
