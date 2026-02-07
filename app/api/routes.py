# app/api/routes.py
from __future__ import annotations

from fastapi import APIRouter

# ✅ به جای ایمپورت تک‌تک روترها، کل پکیج v1 را صدا می‌زنیم
# این متغیر api_router همان چیزی است که در app/api/v1/__init__.py ساختید
from app.api.v1 import api_router as v1_router_module

# ------------------------------------------------------------
# Root API router
# ------------------------------------------------------------
api_router = APIRouter()

@api_router.get("/ping", tags=["system"])
def ping():
    return {"ok": True, "message": "pong", "scope": "api"}


# ------------------------------------------------------------
# V1 Router Registration
# ------------------------------------------------------------
# روتر جمع‌آوری شده در __init__.py را اینجا با پیشوند /v1 وصل می‌کنیم
api_router.include_router(v1_router_module, prefix="/v1")