from __future__ import annotations

import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.dependencies import get_current_admin_user
from app.api.routes import api_router
from app.core.config import settings


def _resolve_api_prefixes() -> tuple[str, str]:
    configured = str(settings.API_PREFIX or "/api").strip()
    if not configured.startswith("/"):
        configured = f"/{configured}"
    configured = configured.rstrip("/")
    if not configured:
        configured = "/api"

    if configured.endswith("/v1"):
        root = configured[: -len("/v1")] or "/api"
        return root, configured

    root = configured
    return root, f"{root}/v1"


ROOT_API_PREFIX, API_V1_PREFIX = _resolve_api_prefixes()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 20, window_seconds: int = 60):
        super().__init__(app)
        self.rate_limit_records = defaultdict(list)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)
        if settings.RATE_LIMIT_SKIP_TESTCLIENT:
            client_host = request.client.host if request.client else ""
            if client_host == "testclient" or settings.is_test_like():
                return await call_next(request)

        if request.url.path.startswith("/api"):
            client_ip = request.client.host if request.client else "unknown"
            current_time = time.time()
            self.rate_limit_records[client_ip] = [
                t for t in self.rate_limit_records[client_ip] if current_time - t < self.window_seconds
            ]
            if len(self.rate_limit_records[client_ip]) >= self.max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                )
            self.rate_limit_records[client_ip].append(current_time)

        return await call_next(request)


class ReadOnlyModeMiddleware(BaseHTTPMiddleware):
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app):
        super().__init__(app)
        api_prefix = API_V1_PREFIX
        self.allowed_paths = {
            f"{api_prefix}/health",
            f"{api_prefix}/auth/login",
        }

    async def dispatch(self, request: Request, call_next):
        if not settings.READ_ONLY_MODE:
            return await call_next(request)

        method = str(request.method or "").upper()
        path = str(request.url.path or "")
        api_prefix = API_V1_PREFIX
        if method in self.WRITE_METHODS and path.startswith(api_prefix) and path not in self.allowed_paths:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "System is in read-only mode for migration/cutover. "
                        "Write operations are temporarily blocked."
                    ),
                },
            )

        return await call_next(request)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runtime DB initialization is intentionally disabled.
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )
    app.add_middleware(ReadOnlyModeMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=int(getattr(settings, "RATE_LIMIT_MAX_REQUESTS", 60)),
        window_seconds=int(getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)),
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        print(f"[ERROR] Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Contact support."},
        )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    else:
        print(f"[WARN] Static directory not found at: {STATIC_DIR}")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) if TEMPLATES_DIR.exists() else None
    if templates is None:
        print(f"[WARN] Templates directory not found at: {TEMPLATES_DIR}")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def home(request: Request):
        if not templates:
            return HTMLResponse("<h1>Error: Templates folder not found!</h1>")
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "app_name": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "api_prefix": API_V1_PREFIX,
                "feature_comm_items_v1": bool(settings.FEATURE_COMM_ITEMS_V1),
            },
        )

    @app.get("/ui/partial/{view_name}", response_class=HTMLResponse, include_in_schema=False)
    async def ui_partial(request: Request, view_name: str):
        if not templates:
            return HTMLResponse("<h1>Error: Templates folder not found!</h1>", status_code=500)

        allowed_views = {
            "dashboard": "views/dashboard.html",
            "edms": "views/edms.html",
            "reports": "views/reports.html",
            "contractor": "views/contractor_hub.html",
            "consultant": "views/consultant_hub.html",
            "edms-settings": "views/module_settings.html",
            "contractor-settings": "views/contractor_module_settings.html",
            "consultant-settings": "views/consultant_module_settings.html",
            "profile": "views/profile_settings.html",
            "settings": "views/settings.html",
        }
        key = str(view_name or "").strip().lower()
        template_name = allowed_views.get(key)
        if not template_name:
            raise HTTPException(status_code=404, detail="Unknown UI partial")

        return templates.TemplateResponse(
            request,
            template_name,
            {
                "app_name": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "api_prefix": API_V1_PREFIX,
                "feature_comm_items_v1": bool(settings.FEATURE_COMM_ITEMS_V1),
            },
        )

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page(request: Request):
        if not templates:
            return HTMLResponse("<h1>Error: Templates folder not found!</h1>")
        return templates.TemplateResponse(request, "login_standalone.html", {})

    @app.get("/debug_login", response_class=HTMLResponse, include_in_schema=False)
    async def debug_login_page(request: Request):
        if not templates:
            return HTMLResponse("<h1>Error: Templates folder not found!</h1>")
        return templates.TemplateResponse(request, "views/debug_login.html", {})

    @app.get(f"{API_V1_PREFIX}/health", tags=["system"])
    def api_health():
        return {"ok": True, "status": "healthy"}

    @app.get(f"{API_V1_PREFIX}/init", tags=["system"])
    def api_init(_: object = Depends(get_current_admin_user)):
        if settings.is_production_like():
            raise HTTPException(
                status_code=403,
                detail="Runtime DB init endpoint is disabled in production-like environments.",
            )
        return {
            "ok": False,
            "detail": "Runtime DB init is disabled. Use `alembic upgrade head` in deployment.",
        }

    app.include_router(api_router, prefix=ROOT_API_PREFIX)

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
