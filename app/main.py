from __future__ import annotations

from pathlib import Path
from contextlib import asynccontextmanager
import time
from collections import defaultdict

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.db.session import init_db, list_tables

# ✅ ایمپورت روتر اصلی (که شامل تمام نسخه‌ها و زیرمجموعه‌هاست)
from app.api.routes import api_router

# ✅ میدل‌ور محدودیت نرخ (Rate Limiter ساده در حافظه)
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 20, window_seconds: int = 60):
        super().__init__(app)
        self.rate_limit_records = defaultdict(list)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next):
        # فقط برای API ها اعمال شود
        if request.url.path.startswith("/api"):
            client_ip = request.client.host
            current_time = time.time()
            # پاکسازی درخواست‌های قدیمی
            self.rate_limit_records[client_ip] = [
                t for t in self.rate_limit_records[client_ip] 
                if current_time - t < self.window_seconds
            ]
            
            if len(self.rate_limit_records[client_ip]) >= self.max_requests:
                return JSONResponse(
                    status_code=429, 
                    content={"detail": "Too many requests. Please try again later."}
                )
            
            self.rate_limit_records[client_ip].append(current_time)
            
        response = await call_next(request)
        return response

# ------------------------------------------------------------
# 1. پیکربندی مسیرها (Paths Configuration)
# ------------------------------------------------------------
# app/main.py -> app -> root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# پوشه‌های templates و static در ریشه پروژه هستند
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"

# ------------------------------------------------------------
# 2. مدیریت چرخه حیات (Lifespan: Startup/Shutdown)
# ------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # اگر در تنظیمات فعال باشد، دیتابیس را چک و ایجاد می‌کند
    if getattr(settings, "AUTO_INIT_DB", False):
        try:
            init_db()
            print("[INFO] DB Initialized automatically.")
        except Exception as e:
            if settings.DEBUG:
                print(f"[WARN] Auto init db failed: {e}")
    
    yield
    # --- Shutdown ---
    pass

# ------------------------------------------------------------
# 3. ساخت اپلیکیشن (App Factory)
# ------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )
    
    # اضافه کردن میدل‌ور
    app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60) # 60 درخواست در دقیقه

    # ✅ هندلر مرکزی خطاها
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        print(f"❌ Unhandled Error: {exc}")  # اینجا می‌توانید لاگ کنید
        return JSONResponse(
            status_code=500,
            content={"detail": "خطای داخلی سرور. لطفاً با پشتیبانی تماس بگیرید."}
        )

    # 1. اتصال فایل‌های استاتیک (CSS, JS, Images)
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    else:
        print(f"[WARN] Static directory not found at: {STATIC_DIR}")

    # 2. راه‌اندازی موتور قالب‌ساز (Jinja2)
    templates = None
    if TEMPLATES_DIR.exists():
        templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    else:
        print(f"[WARN] Templates directory not found at: {TEMPLATES_DIR}")

    # -----------------------------
    # مسیر صفحه اصلی (Web Pages)
    # -----------------------------
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def home(request: Request):
        """صفحه اصلی داشبورد"""
        if not templates:
            return HTMLResponse("<h1>Error: Templates folder not found!</h1>")
        
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "app_name": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "api_prefix": settings.API_PREFIX,
            },
        )

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page(request: Request):
        """صفحه ورود به سیستم - کاملاً ایزوله"""
        if not templates:
            return HTMLResponse("<h1>Error: Templates folder not found!</h1>")
        
        return templates.TemplateResponse(
            request,
            "login_standalone.html",
            {}
        )

    @app.get("/debug_login", response_class=HTMLResponse, include_in_schema=False)
    async def debug_login_page(request: Request):
        """صفحه دیباگ لاگین ایزوله"""
        if not templates:
            return HTMLResponse("<h1>Error: Templates folder not found!</h1>")
        
        return templates.TemplateResponse(
            request,
            "views/debug_login.html",
            {}
        )

    # -----------------------------
    # اندپوینت‌های سیستمی (Health & Init)
    # -----------------------------
    @app.get(f"{settings.API_PREFIX}/health", tags=["system"])
    def api_health():
        return {"ok": True, "status": "healthy"}

    @app.get(f"{settings.API_PREFIX}/init", tags=["system"])
    def api_init():
        """Force init DB manually"""
        try:
            init_db()
            return {"ok": True, "message": "DB initialized"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}

    # -----------------------------
    # ثبت روترهای API
    # -----------------------------
    app.include_router(api_router, prefix=settings.API_PREFIX)

    # -----------------------------
    # هندلرهای خطا (Error Handlers)
    # -----------------------------
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return JSONResponse(
            status_code=404,
            content={"detail": "Not found"}
        )

    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc):
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

    return app

# ------------------------------------------------------------
# 4. ساخت اپلیکیشن برای اجرا
# ------------------------------------------------------------
app = create_app()

# ------------------------------------------------------------
# 5. اجرای مستقیم (برای توسعه)
# ------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
