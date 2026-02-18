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


def test_storage_openproject_ping_401_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "https://open-project.example.com")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(401)

    monkeypatch.setattr(requests, "get", _fake_get)

    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is True
    assert body.get("auth_ok") is False
    assert body.get("status_code") == 401
    assert body.get("token_source") == "env"


def test_storage_openproject_ping_403_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "https://open-project.example.com")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(403)

    monkeypatch.setattr(requests, "get", _fake_get)

    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is True
    assert body.get("auth_ok") is False
    assert body.get("status_code") == 403
    assert body.get("token_source") == "env"


def test_storage_openproject_ping_200_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "https://open-project.example.com")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "get", _fake_get)

    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is True
    assert body.get("auth_ok") is True
    assert body.get("status_code") == 200
    assert body.get("token_source") == "env"


def test_storage_openproject_ping_404_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "https://open-project.example.com/openproject")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token")

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(404)

    monkeypatch.setattr(requests, "get", _fake_get)

    res = client.post("/api/v1/storage/openproject/ping", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reachable") is True
    assert body.get("auth_ok") is False
    assert body.get("status_code") == 404
    assert "path not found" in str(body.get("message") or "").lower()


def test_storage_openproject_ping_timeout_semantics(monkeypatch) -> None:
    headers = _admin_headers()
    monkeypatch.setattr(settings, "OPENPROJECT_BASE_URL", "https://open-project.example.com")
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "")

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
