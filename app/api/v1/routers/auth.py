from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.db import models
from app.core import security
from app.core.roles import Role, normalize_role
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

    tabs = {
        "archive": dependencies.has_permission_for_user(db, current_user, "archive:read"),
        "transmittal": dependencies.has_permission_for_user(db, current_user, "transmittal:read"),
        "correspondence": dependencies.has_permission_for_user(db, current_user, "correspondence:read"),
        "reports": dependencies.has_permission_for_user(db, current_user, "reports:read"),
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

    return {
        "ok": True,
        "edms_tabs": tabs,
        "default_edms_tab": default_tab,
    }


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

    current_user.hashed_password = security.get_password_hash(password_data.new_password)
    db.commit()

    return {"ok": True, "message": "رمز عبور با موفقیت تغییر کرد"}
