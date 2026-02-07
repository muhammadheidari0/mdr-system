from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings


def get_test_admin_credentials() -> tuple[str, str]:
    email = (settings.TEST_ADMIN_EMAIL or "").strip()
    password = (settings.TEST_ADMIN_PASSWORD or "").strip()

    missing = []
    if not email:
        missing.append("TEST_ADMIN_EMAIL")
    if not password:
        missing.append("TEST_ADMIN_PASSWORD")

    if missing:
        env_path = Path(settings.BASE_DIR) / ".env"
        missing_vars = ", ".join(missing)
        pytest.fail(
            f"Missing required test auth env var(s): {missing_vars}. "
            f"Set them in environment or in {env_path} for CI/CD auth endpoint tests."
        )

    return email, password


def get_auth_headers(client) -> dict[str, str]:
    email, password = get_test_admin_credentials()
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        env_path = Path(settings.BASE_DIR) / ".env"
        pytest.fail(
            "Test admin login failed. "
            f"email={email!r}, status={response.status_code}, body={response.text}. "
            "Sync DB admin credentials with env values (ADMIN_EMAIL/ADMIN_PASSWORD and "
            f"TEST_ADMIN_EMAIL/TEST_ADMIN_PASSWORD), then run `python create_admin.py`. "
            f"Config file: {env_path}"
        )
    token = response.json().get("access_token")
    if not token:
        pytest.fail("Auth response did not contain access_token for test admin user.")
    return {"Authorization": f"Bearer {token}"}
