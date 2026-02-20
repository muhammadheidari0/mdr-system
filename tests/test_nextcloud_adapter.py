from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from app.services.nextcloud_adapter import NextcloudAdapter


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def test_nextcloud_adapter_normalization() -> None:
    adapter = NextcloudAdapter(
        base_url="https://nextcloud.example.com/root/",
        username="integration.user",
        app_password="secret",
        root_path="\\mdr\\files\\",
    )
    assert adapter.base_url == "https://nextcloud.example.com/root"
    assert adapter.root_path == "/mdr/files"
    assert (
        adapter.build_webdav_root_url()
        == "https://nextcloud.example.com/root/remote.php/dav/files/integration.user/mdr/files"
    )


def test_nextcloud_adapter_ping_respects_tls_verify(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        captured["method"] = method
        captured["url"] = url
        captured["verify"] = kwargs.get("verify")
        return _FakeResponse(207)

    monkeypatch.setattr(requests, "request", _fake_request)
    adapter = NextcloudAdapter(
        base_url="https://nextcloud.example.com",
        username="nc-user",
        app_password="secret",
        root_path="/mdr",
        tls_verify=False,
    )
    result = adapter.ping()
    assert result.get("status_code") == 207
    assert result.get("ok") is True
    assert captured.get("method") == "PROPFIND"
    assert captured.get("verify") is False


def test_nextcloud_adapter_upload_file_creates_path_and_uploads(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        calls.append((method, url))
        if method == "MKCOL":
            return _FakeResponse(201)
        if method == "PUT":
            return _FakeResponse(201)
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "request", _fake_request)

    local_file = tmp_path / "sample.txt"
    local_file.write_text("nextcloud-mirror-content", encoding="utf-8")

    adapter = NextcloudAdapter(
        base_url="https://nextcloud.example.com",
        username="nc-user",
        app_password="secret",
        root_path="/mdr",
    )
    result = adapter.upload_file(
        local_path=str(local_file),
        remote_relative_path="archive/T202/AR/2026/02/sample.txt",
    )
    assert result.get("remote_id") == "archive/T202/AR/2026/02/sample.txt"
    assert str(result.get("remote_url") or "").endswith("/archive/T202/AR/2026/02/sample.txt")
    methods = [method for method, _url in calls]
    assert "MKCOL" in methods
    assert "PUT" in methods
