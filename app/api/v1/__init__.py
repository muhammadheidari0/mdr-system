from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers.archive import router as archive_router
from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.bim import router as bim_router
from app.api.v1.routers.communication_items import router as communication_items_router
from app.api.v1.routers.correspondence import router as correspondence_router
from app.api.v1.routers.dashboard import router as dashboard_router
from app.api.v1.routers.edms_forms import router as edms_forms_router
from app.api.v1.routers.edms_sync_admin import router as edms_sync_admin_router
from app.api.v1.routers.lookup import router as lookup_router
from app.api.v1.routers.meeting_minutes import router as meeting_minutes_router
from app.api.v1.routers.mdr import router as mdr_router
from app.api.v1.routers.permit_qc import router as permit_qc_router
from app.api.v1.routers.project_control import router as project_control_router
from app.api.v1.routers.site_logs import router as site_logs_router
from app.api.v1.routers.site_cache import router as site_cache_router
from app.api.v1.routers.settings import router as settings_router
from app.api.v1.routers.storage import router as storage_router
from app.api.v1.routers.transmittal import router as transmittal_router
from app.api.v1.routers.users import router as users_router
from app.api.v1.routers.work_instructions import router as work_instructions_router
from app.api.v1.routers.workboard import router as workboard_router

api_router = APIRouter()

api_router.include_router(lookup_router)
api_router.include_router(settings_router)
api_router.include_router(site_cache_router)
api_router.include_router(storage_router)
api_router.include_router(edms_sync_admin_router)
api_router.include_router(mdr_router)
api_router.include_router(archive_router)
api_router.include_router(transmittal_router)
api_router.include_router(dashboard_router)
api_router.include_router(edms_forms_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(correspondence_router)
api_router.include_router(meeting_minutes_router)
api_router.include_router(workboard_router)
api_router.include_router(communication_items_router)
api_router.include_router(work_instructions_router)
api_router.include_router(permit_qc_router)
api_router.include_router(project_control_router)
api_router.include_router(site_logs_router)
api_router.include_router(bim_router)
