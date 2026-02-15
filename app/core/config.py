# app/core/config.py
from __future__ import annotations

import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> app/core -> app -> ROOT (mdr_app)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BASE_DIR: Path = _PROJECT_ROOT

    APP_NAME: str = "MDR App"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    APP_ENV: str = "development"

    API_PREFIX: str = "/api/v1"

    # DB
    DATABASE_URL: str = "postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app"
    READ_ONLY_MODE: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_ECHO: bool = False
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_SKIP_TESTCLIENT: bool = True

    # Paths
    TEMPLATES_DIR: str = "templates"
    STATIC_DIR: str = "static"

    # Security
    SECRET_KEY: str = Field(default="")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Storage Integrations
    GDRIVE_SERVICE_ACCOUNT_JSON: str = ""
    GDRIVE_SHARED_DRIVE_ID: str = ""
    OPENPROJECT_BASE_URL: str = ""
    OPENPROJECT_API_TOKEN: str = ""
    OPENPROJECT_DEFAULT_PROJECT_ID: str = ""

    # Test auth (read from .env or process environment)
    TEST_ADMIN_EMAIL: str | None = None
    TEST_ADMIN_PASSWORD: str | None = None

    def is_production_like(self) -> bool:
        env = str(self.APP_ENV or "").strip().lower()
        return env in {"prod", "production", "staging"}

    def is_test_like(self) -> bool:
        env = str(self.APP_ENV or "").strip().lower()
        if env in {"test", "testing", "pytest"}:
            return True
        return bool(os.getenv("PYTEST_CURRENT_TEST"))

    def masked_database_url(self) -> str:
        value = str(self.DATABASE_URL or "").strip()
        if not value:
            return ""
        if "://" not in value:
            return value
        # Keep scheme and netloc shape; hide secrets if present.
        try:
            scheme, rest = value.split("://", 1)
            if "@" not in rest:
                return value
            auth, host = rest.split("@", 1)
            if ":" in auth:
                user, _ = auth.split(":", 1)
                return f"{scheme}://{user}:***@{host}"
            return f"{scheme}://***@{host}"
        except Exception:
            return value


settings = Settings()
