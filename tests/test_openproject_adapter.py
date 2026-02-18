from __future__ import annotations

from typing import Any

import requests

from app.services.openproject_adapter import OpenProjectAdapter


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


def test_openproject_base_url_normalization_variants() -> None:
    assert OpenProjectAdapter.normalize_base_url("https://host") == "https://host"
    assert OpenProjectAdapter.normalize_base_url("https://host/") == "https://host"
    assert OpenProjectAdapter.normalize_base_url("https://host/openproject") == "https://host/openproject"
    assert OpenProjectAdapter.normalize_base_url("https://host/openproject/api/v3") == "https://host/openproject"


def test_openproject_adapter_uses_basic_auth_with_timeouts_and_tls(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        captured["method"] = method
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(requests, "request", _fake_request)

    adapter = OpenProjectAdapter(
        base_url="https://open-project.example.com/api/v3",
        api_token="token-123",
        connect_timeout=7,
        read_timeout=13,
        tls_verify=True,
    )
    body = adapter.ping()

    assert body.get("ok") is True
    assert captured["method"] == "GET"
    assert captured["url"] == "https://open-project.example.com/api/v3"
    assert captured["kwargs"]["auth"] == ("apikey", "token-123")
    assert tuple(captured["kwargs"]["timeout"]) == (7.0, 13.0)
    assert captured["kwargs"]["verify"] is True


def test_openproject_adapter_attach_external_link_contract(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        captured["method"] = method
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse(200, {"id": "987"})

    monkeypatch.setattr(requests, "request", _fake_request)

    adapter = OpenProjectAdapter(base_url="https://open-project.example.com", api_token="token-abc")
    response = adapter.attach_external_link(
        work_package_id=321,
        title="Attachment Title",
        url="https://files.local/item/1",
    )

    assert response.get("id") == "987"
    assert captured["method"] == "PATCH"
    assert captured["url"] == "https://open-project.example.com/api/v3/work_packages/321"
    assert captured["kwargs"]["auth"] == ("apikey", "token-abc")
    payload = captured["kwargs"]["json"]
    assert payload["description"]["raw"].startswith("Attachment Title")
