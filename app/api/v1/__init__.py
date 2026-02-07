# app/api/v1/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers.lookup import router as lookup_router
from app.api.v1.routers.settings import router as settings_router
from app.api.v1.routers.mdr import router as mdr_router
from app.api.v1.routers.archive import router as archive_router
from app.api.v1.routers.transmittal import router as transmittal_router
from app.api.v1.routers.dashboard import router as dashboard_router  # ✅ اضافه شد (روتر جدید داشبورد)
from app.api.v1.routers.auth import router as auth_router  # ✅ اضافه شد (روتر احراز هویت)
from app.api.v1.routers.users import router as users_router  # ✅ اضافه شد (روتر مدیریت کاربران)
from app.api.v1.routers.correspondence import router as correspondence_router

api_router = APIRouter()

# ثبت تمام روترها در روتر اصلی نسخه 1
api_router.include_router(lookup_router)
api_router.include_router(settings_router)
api_router.include_router(mdr_router)
api_router.include_router(archive_router)
api_router.include_router(transmittal_router)
api_router.include_router(dashboard_router)  # ✅ اضافه شد
api_router.include_router(auth_router)  # ✅ اضافه شد
api_router.include_router(users_router)  # ✅ اضافه شد
api_router.include_router(correspondence_router)
