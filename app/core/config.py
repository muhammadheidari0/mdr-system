# app/core/config.py
from __future__ import annotations

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

    API_PREFIX: str = "/api/v1"

    # DB
    DATABASE_URL: str = "sqlite:///./database/mdr_project.db"
    AUTO_INIT_DB: bool = True

    # Paths
    TEMPLATES_DIR: str = "templates"
    STATIC_DIR: str = "static"

    # Security
    SECRET_KEY: str = Field(default="")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Test auth (read from .env or process environment)
    TEST_ADMIN_EMAIL: str | None = None
    TEST_ADMIN_PASSWORD: str | None = None


settings = Settings()
