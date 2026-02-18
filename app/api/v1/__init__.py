from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers.archive import router as archive_router
from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.communication_items import router as communication_items_router
from app.api.v1.routers.correspondence import router as correspondence_router
from app.api.v1.routers.dashboard import router as dashboard_router
from app.api.v1.routers.lookup import router as lookup_router
from app.api.v1.routers.mdr import router as mdr_router
from app.api.v1.routers.site_logs import router as site_logs_router
from app.api.v1.routers.site_cache import router as site_cache_router
from app.api.v1.routers.settings import router as settings_router
from app.api.v1.routers.storage import router as storage_router
from app.api.v1.routers.transmittal import router as transmittal_router
from app.api.v1.routers.users import router as users_router
from app.api.v1.routers.workboard import router as workboard_router

api_router = APIRouter()

api_router.include_router(lookup_router)
api_router.include_router(settings_router)
api_router.include_router(site_cache_router)
api_router.include_router(storage_router)
api_router.include_router(mdr_router)
api_router.include_router(archive_router)
api_router.include_router(transmittal_router)
api_router.include_router(dashboard_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(correspondence_router)
api_router.include_router(workboard_router)
api_router.include_router(communication_items_router)
api_router.include_router(site_logs_router)
