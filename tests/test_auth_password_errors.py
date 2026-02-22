from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import get_auth_headers, get_test_admin_credentials

client = TestClient(app)


def test_change_password_returns_400_for_password_over_72_bytes() -> None:
    headers = get_auth_headers(client)
    _, current_password = get_test_admin_credentials()
    too_long = "a" * 73

    response = client.post(
        "/api/v1/auth/change-password",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "current_password": current_password,
            "new_password": too_long,
        },
    )
    assert response.status_code == 400, response.text
    detail = str(response.json().get("detail") or "")
    assert "72-byte" in detail


def test_create_user_returns_400_for_password_over_72_bytes() -> None:
    headers = get_auth_headers(client)
    response = client.post(
        "/api/v1/users/",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "email": "long-password-user@example.com",
            "full_name": "Long Password User",
            "password": "a" * 73,
            "role": "user",
            "organization_role": "viewer",
            "is_active": True,
        },
    )
    assert response.status_code == 400, response.text
    detail = str(response.json().get("detail") or "")
    assert "72-byte" in detail
