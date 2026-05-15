import json
from datetime import timedelta
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api import dependencies
from app.core.config import settings
from app.core import security
from app.core.access_matrix import build_navigation_state
from app.core.permission_catalog import permission_keys
from app.db import models
from app.schemas import auth as auth_schemas
from app.services.access_control import resolve_effective_access

router = APIRouter(prefix="/auth", tags=["Authentication"])
bearer_scheme = HTTPBearer(auto_error=False)

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
    
    access_token_expires = timedelta(minutes=max(1, int(settings.ACCESS_TOKEN_EXPIRE_MINUTES or 43200)))
    access = resolve_effective_access(user)
    
    # ساخت توکن
    access_token = security.create_access_token(
        data={"sub": user.email, "role": access.effective_role},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(dependencies.get_db),
):
    if credentials and credentials.credentials:
        dependencies.revoke_auth_session(db, credentials.credentials)
    return {"ok": True}

@router.get("/me", response_model=auth_schemas.AuthMeResponse)
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
        "idle_timeout_minutes": dependencies.auth_idle_timeout_minutes(),
        "heartbeat_interval_seconds": dependencies.auth_heartbeat_interval_seconds(),
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

    # --- Bulk permission check: single DB round-trip ---
    all_permissions = permission_keys()
    p = dependencies.bulk_check_permissions_for_user(db, current_user, all_permissions)

    # Cache key must track the effective permission set itself; otherwise a matrix
    # update for the same role/category/user org can leave stale hub/tab visibility
    # in the browser and produce 403s on first load.
    granted_permissions = sorted(permission for permission, allowed in p.items() if allowed)
    etag_payload = {
        "user_id": getattr(current_user, "id", 0) or 0,
        "organization_id": getattr(current_user, "organization_id", 0) or 0,
        "role": user_role,
        "category": category,
        "granted": granted_permissions,
    }
    etag = f'W/"{sha256(json.dumps(etag_payload, sort_keys=True).encode()).hexdigest()[:16]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    navigation_state = build_navigation_state(
        p,
        category=category,
        effective_role=user_role,
    )
    module_settings_visibility = navigation_state["module_settings_visibility"]
    module_settings_allowed = any(bool(value) for value in module_settings_visibility.values())

    response_data = {
        "ok": True,
        "category": category,
        "effective_role": access.effective_role,
        "permission_category": access.permission_category,
        "organization_type": access.organization_type,
        "is_system_admin": access.is_system_admin,
        "capabilities": p,
        "hubs": navigation_state["hubs"],
        "default_hub": navigation_state["default_hub"],
        "modules": navigation_state["modules"],
        "contractor_tabs": navigation_state["contractor_tabs"],
        "consultant_tabs": navigation_state["consultant_tabs"],
        "edms_tabs": navigation_state["edms_tabs"],
        "default_edms_tab": navigation_state["default_edms_tab"],
        "module_settings": module_settings_allowed,
        "module_settings_visibility": navigation_state["module_settings_visibility"],
    }
    # Backward compatibility for legacy clients expecting per-hub module-settings flags.
    response_data["edms"] = bool(module_settings_visibility.get("edms"))
    response_data["contractor"] = bool(module_settings_visibility.get("contractor"))
    response_data["consultant"] = bool(module_settings_visibility.get("consultant"))

    return Response(
        content=json.dumps(response_data),
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "private, no-cache"},
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
