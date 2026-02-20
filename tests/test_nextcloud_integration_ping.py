from __future__ import annotations

from typing import Any

import requests
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.nextcloud_adapter import NextcloudAdapter
from tests.auth_helpers import get_auth_headers

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _patch_integrations(monkeypatch, **nextcloud: Any) -> None:
    payload = {
        "mirror": {"provider": "nextcloud"},
        "google_drive": {"enabled": False},
        "openproject": {"enabled": False},
        "nextcloud": {
            "enabled": True,
            "base_url": "",
            "username": "",
            "app_password": "",
            "root_path": "/",
            **nextcloud,
        },
        "local_cache": {"enabled": True},
    }
    monkeypatch.setattr("app.api.v1.routers.storage.get_storage_integrations", lambda _db: payload)


def test_nextcloud_ping_401_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "NEXTCLOUD_BASE_URL", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY_FORCE", "")
    _patch_integrations(
        monkeypatch,
        base_url="https://nextcloud.example.com",
        username="nc-user",
        app_password="nc-pass",
        skip_ssl_verify=False,
    )
    monkeypatch.setattr(NextcloudAdapter, "ping_raw", lambda self: _FakeResponse(401))

    res = client.post("/api/v1/storage/nextcloud/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is True
    assert body.get("auth_ok") is False
    assert body.get("status_code") == 401
    assert body.get("credential_source") == "settings"
    assert body.get("ssl_source") == "settings"
    assert body.get("tls_verify_effective") is True


def test_nextcloud_ping_404_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "NEXTCLOUD_BASE_URL", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY_FORCE", "")
    _patch_integrations(
        monkeypatch,
        base_url="https://nextcloud.example.com",
        username="nc-user",
        app_password="nc-pass",
    )
    monkeypatch.setattr(NextcloudAdapter, "ping_raw", lambda self: _FakeResponse(404))

    res = client.post("/api/v1/storage/nextcloud/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is True
    assert body.get("auth_ok") is False
    assert body.get("status_code") == 404
    assert "path not found" in str(body.get("message") or "").lower()


def test_nextcloud_ping_timeout_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "NEXTCLOUD_BASE_URL", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY_FORCE", "")
    _patch_integrations(
        monkeypatch,
        base_url="https://nextcloud.example.com",
        username="nc-user",
        app_password="nc-pass",
    )

    def _raise_timeout(self):
        raise requests.Timeout("timeout")

    monkeypatch.setattr(NextcloudAdapter, "ping_raw", _raise_timeout)
    res = client.post("/api/v1/storage/nextcloud/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is False
    assert body.get("auth_ok") is False
    assert body.get("status_code") is None


def test_nextcloud_ping_uses_request_overrides(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "NEXTCLOUD_BASE_URL", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY_FORCE", "")
    _patch_integrations(monkeypatch, enabled=True, base_url="", username="", app_password="")

    captured: dict[str, Any] = {}

    def _fake_ping_raw(self):
        captured["base_url"] = self.base_url
        captured["username"] = self.username
        captured["root_path"] = self.root_path
        captured["tls_verify"] = self.tls_verify
        return _FakeResponse(200)

    monkeypatch.setattr(NextcloudAdapter, "ping_raw", _fake_ping_raw)
    res = client.post(
        "/api/v1/storage/nextcloud/ping",
        headers=headers,
        json={
            "base_url": "https://nextcloud.example.com",
            "username": "override-user",
            "app_password": "override-pass",
            "root_path": "/edms",
            "skip_ssl_verify": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is True
    assert body.get("auth_ok") is True
    assert body.get("ssl_source") == "settings"
    assert body.get("tls_verify_effective") is False
    assert captured.get("base_url") == "https://nextcloud.example.com"
    assert captured.get("username") == "override-user"
    assert captured.get("root_path") == "/edms"
    assert captured.get("tls_verify") is False
