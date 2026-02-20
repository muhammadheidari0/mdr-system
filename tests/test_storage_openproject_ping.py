from __future__ import annotations

from typing import Any

import requests
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from tests.auth_helpers import get_auth_headers

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _patch_integrations(monkeypatch, **openproject: Any) -> None:
    payload = {
        "google_drive": {"enabled": False},
        "openproject": {
            "enabled": True,
            "base_url": "",
            "api_token": "",
            "default_work_package_id": "",
            **openproject,
        },
        "local_cache": {"enabled": True},
    }
    monkeypatch.setattr("app.api.v1.routers.storage.get_storage_integrations", lambda _db: payload)


def test_storage_openproject_ping_401_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "https://open-project.example.com")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "")
    _patch_integrations(monkeypatch)

    captured: dict[str, Any] = {}

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        captured["verify"] = kwargs.get("verify")
        return _FakeResponse(401)

    monkeypatch.setattr(requests, "get", _fake_get)

    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is True
    assert body.get("auth_ok") is False
    assert body.get("status_code") == 401
    assert body.get("token_source") == "env"
    assert body.get("ssl_source") == "env_default"
    assert body.get("tls_verify_effective") is True
    assert captured.get("verify") is True


def test_storage_openproject_ping_404_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "https://open-project.example.com/openproject")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "")
    _patch_integrations(monkeypatch)

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(404)

    monkeypatch.setattr(requests, "get", _fake_get)

    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is True
    assert body.get("auth_ok") is False
    assert body.get("status_code") == 404
    assert body.get("ssl_source") == "env_default"
    assert body.get("tls_verify_effective") is True
    assert "path not found" in str(body.get("message") or "").lower()


def test_storage_openproject_ping_timeout_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "https://open-project.example.com")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "")
    _patch_integrations(monkeypatch)

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        raise requests.Timeout("timeout")

    monkeypatch.setattr(requests, "get", _fake_get)

    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is False
    assert body.get("auth_ok") is False
    assert body.get("status_code") is None
    assert body.get("token_source") in {"none", "settings"}
    assert body.get("ssl_source") == "env_default"
    assert body.get("tls_verify_effective") is True


def test_storage_openproject_ping_precedence_force_true(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "https://open-project.example.com")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", False)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "true")
    _patch_integrations(monkeypatch, skip_ssl_verify=True)

    captured: dict[str, Any] = {}

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        captured["verify"] = kwargs.get("verify")
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "get", _fake_get)
    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("auth_ok") is True
    assert body.get("ssl_source") == "env_force"
    assert body.get("tls_verify_effective") is True
    assert captured.get("verify") is True


def test_storage_openproject_ping_precedence_force_false(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "https://open-project.example.com")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "0")
    _patch_integrations(monkeypatch, skip_ssl_verify=False)

    captured: dict[str, Any] = {}

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        captured["verify"] = kwargs.get("verify")
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "get", _fake_get)
    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("auth_ok") is True
    assert body.get("ssl_source") == "env_force"
    assert body.get("tls_verify_effective") is False
    assert captured.get("verify") is False


def test_storage_openproject_ping_precedence_ui_skip_true(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "")
    _patch_integrations(monkeypatch, base_url="https://open-project.example.com", skip_ssl_verify=True)

    captured: dict[str, Any] = {}

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        captured["verify"] = kwargs.get("verify")
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "get", _fake_get)
    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ssl_source") == "settings"
    assert body.get("tls_verify_effective") is False
    assert captured.get("verify") is False


def test_storage_openproject_ping_precedence_ui_skip_false(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", False)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "")
    _patch_integrations(monkeypatch, base_url="https://open-project.example.com", skip_ssl_verify=False)

    captured: dict[str, Any] = {}

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        captured["verify"] = kwargs.get("verify")
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "get", _fake_get)
    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ssl_source") == "settings"
    assert body.get("tls_verify_effective") is True
    assert captured.get("verify") is True


def test_storage_openproject_ping_precedence_env_default_when_ui_missing(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", False)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "")
    _patch_integrations(monkeypatch, base_url="https://open-project.example.com")

    captured: dict[str, Any] = {}

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        captured["verify"] = kwargs.get("verify")
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "get", _fake_get)
    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ssl_source") == "env_default"
    assert body.get("tls_verify_effective") is False
    assert captured.get("verify") is False


def test_storage_openproject_ping_uses_request_overrides_without_save(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "")
    _patch_integrations(monkeypatch, base_url="", api_token="", skip_ssl_verify=False)

    captured: dict[str, Any] = {}

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        captured["url"] = args[0] if args else ""
        captured["verify"] = kwargs.get("verify")
        captured["auth"] = kwargs.get("auth")
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "get", _fake_get)
    res = client.post(
        "/api/v1/storage/openproject/ping",
        headers=headers,
        json={
            "base_url": "https://open-project.example.com/openproject",
            "api_token": "request-token-1",
            "skip_ssl_verify": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("auth_ok") is True
    assert body.get("token_source") == "settings"
    assert body.get("ssl_source") == "settings"
    assert body.get("tls_verify_effective") is False
    assert captured.get("verify") is False
    assert captured.get("auth") == ("apikey", "request-token-1")
    assert captured.get("url") == "https://open-project.example.com/openproject/api/v3"
