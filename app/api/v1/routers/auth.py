from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.db import models
from app.core import security
from app.core.roles import Role, normalize_role
from app.core.organizations import OrganizationType, resolve_user_permission_category
from app.schemas import auth as auth_schemas
from app.api import dependencies

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
    
    # ساخت توکن
    access_token = security.create_access_token(
        data={"sub": user.email, "role": user.role},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=auth_schemas.UserResponse)
# اصلاح این خط: استفاده از dependencies.get_current_user به جای security.get_current_user
def read_users_me(current_user: models.User = Depends(dependencies.get_current_user)):
    return current_user


@router.get("/navigation")
def get_navigation(
    db: Session = Depends(dependencies.get_db),
    current_user: models.User = Depends(dependencies.get_current_user),
):
    user_role = normalize_role(current_user.role)
    category = resolve_user_permission_category(current_user)

    module_settings_allowed = dependencies.has_permission_for_user(db, current_user, "module_settings:read")

    modules = {
        "edms": {
            "archive": dependencies.has_permission_for_user(db, current_user, "module_archive:read")
            and dependencies.has_permission_for_user(db, current_user, "archive:read"),
            "transmittal": dependencies.has_permission_for_user(db, current_user, "module_transmittal:read")
            and dependencies.has_permission_for_user(db, current_user, "transmittal:read"),
            "correspondence": dependencies.has_permission_for_user(db, current_user, "module_correspondence:read")
            and dependencies.has_permission_for_user(db, current_user, "correspondence:read"),
        },
        "reports": {
            "overview": dependencies.has_permission_for_user(db, current_user, "module_reports:read")
            and dependencies.has_permission_for_user(db, current_user, "reports:read"),
        },
        "contractor": {
            "execution": dependencies.has_permission_for_user(db, current_user, "module_site_logs_contractor:read"),
            "requests": dependencies.has_permission_for_user(db, current_user, "module_comm_items_contractor:read"),
            "permit_qc": dependencies.has_permission_for_user(db, current_user, "module_permit_qc_contractor:read"),
        },
        "consultant": {
            "inspection": dependencies.has_permission_for_user(db, current_user, "module_site_logs_consultant:read"),
            "defects": dependencies.has_permission_for_user(db, current_user, "module_comm_items_consultant:read"),
            "instructions": dependencies.has_permission_for_user(db, current_user, "module_comm_items_consultant:read"),
            "control": dependencies.has_permission_for_user(db, current_user, "module_comm_items_consultant:read"),
            "permit_qc": dependencies.has_permission_for_user(db, current_user, "module_permit_qc_consultant:read"),
        },
        "settings": {
            "module_settings": module_settings_allowed,
        },
    }

    hubs = {
        "dashboard": dependencies.has_permission_for_user(db, current_user, "dashboard:read"),
        "edms": dependencies.has_permission_for_user(db, current_user, "hub_edms:read")
        and any(bool(v) for v in modules["edms"].values()),
        "reports": dependencies.has_permission_for_user(db, current_user, "hub_reports:read")
        and bool(modules["reports"].get("overview")),
        "contractor": dependencies.has_permission_for_user(db, current_user, "hub_contractor:read")
        and any(bool(v) for v in modules["contractor"].values()),
        "consultant": dependencies.has_permission_for_user(db, current_user, "hub_consultant:read")
        and any(bool(v) for v in modules["consultant"].values()),
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

    response = {
        "ok": True,
        "category": category,
        "hubs": hubs,
        "default_hub": default_hub,
        "modules": modules,
        "edms_tabs": tabs,
        "default_edms_tab": default_tab,
        "module_settings": module_settings_allowed,
    }
    # Backward compatibility for legacy clients expecting per-hub module-settings flags.
    response["edms"] = module_settings_allowed
    response["contractor"] = module_settings_allowed
    response["consultant"] = module_settings_allowed
    return response


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
