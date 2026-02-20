from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.google_oauth_adapter import GoogleOAuthAdapter
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def test_google_ping_services_contract(monkeypatch) -> None:
    headers = _admin_headers()

    def _fake_ping(self, service: str):
        key = str(service or "").strip().lower()
        if key == "drive":
            return {
                "service": "drive",
                "reachable": True,
                "auth_ok": True,
                "status_code": 200,
                "message": "ok",
            }
        if key == "gmail":
            return {
                "service": "gmail",
                "reachable": True,
                "auth_ok": False,
                "status_code": 403,
                "message": "forbidden",
            }
        return {
            "service": "calendar",
            "reachable": False,
            "auth_ok": False,
            "status_code": None,
            "message": "timeout",
        }

    monkeypatch.setattr(GoogleOAuthAdapter, "ping", _fake_ping)

    drive_res = client.post(
        "/api/v1/storage/google/ping",
        headers=headers,
        json={
            "service": "drive",
            "oauth_client_id": "client-id",
            "oauth_client_secret": "client-secret",
            "oauth_refresh_token": "refresh-token",
        },
    )
    assert drive_res.status_code == 200, drive_res.text
    drive = drive_res.json()
    assert drive.get("ok") is True
    assert drive.get("service") == "drive"
    assert drive.get("reachable") is True
    assert drive.get("auth_ok") is True
    assert int(drive.get("status_code") or 0) == 200

    gmail_res = client.post(
        "/api/v1/storage/google/ping",
        headers=headers,
        json={
            "service": "gmail",
            "oauth_client_id": "client-id",
            "oauth_client_secret": "client-secret",
            "oauth_refresh_token": "refresh-token",
            "sender_email": "sender@example.com",
        },
    )
    assert gmail_res.status_code == 200, gmail_res.text
    gmail = gmail_res.json()
    assert gmail.get("ok") is True
    assert gmail.get("service") == "gmail"
    assert gmail.get("reachable") is True
    assert gmail.get("auth_ok") is False
    assert int(gmail.get("status_code") or 0) == 403

    cal_res = client.post(
        "/api/v1/storage/google/ping",
        headers=headers,
        json={
            "service": "calendar",
            "oauth_client_id": "client-id",
            "oauth_client_secret": "client-secret",
            "oauth_refresh_token": "refresh-token",
            "calendar_id": "calendar-1",
        },
    )
    assert cal_res.status_code == 200, cal_res.text
    calendar = cal_res.json()
    assert calendar.get("ok") is True
    assert calendar.get("service") == "calendar"
    assert calendar.get("reachable") is False
    assert calendar.get("auth_ok") is False
    assert calendar.get("status_code") is None


def test_google_ping_invalid_service_returns_400() -> None:
    headers = _admin_headers()
    res = client.post(
        "/api/v1/storage/google/ping",
        headers=headers,
        json={"service": "invalid"},
    )
    assert res.status_code == 400, res.text


def test_google_ping_runtime_error_returns_unreachable(monkeypatch) -> None:
    headers = _admin_headers()

    def _raise_runtime(self, service: str):
        del service
        raise RuntimeError("Google OAuth client_id is required.")

    monkeypatch.setattr(GoogleOAuthAdapter, "ping", _raise_runtime)
    res = client.post(
        "/api/v1/storage/google/ping",
        headers=headers,
        json={"service": "drive"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    assert body.get("reachable") is False
    assert body.get("auth_ok") is False
    assert body.get("status_code") is None
    assert "required" in str(body.get("message") or "").lower()
