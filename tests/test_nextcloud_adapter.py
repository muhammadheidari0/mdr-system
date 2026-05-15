from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from app.services.nextcloud_adapter import NextcloudAdapter


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "", json_payload: Any | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self._json_payload = json_payload

    def json(self) -> Any:
        if self._json_payload is not None:
            return self._json_payload
        raise ValueError("No JSON payload")


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


def test_nextcloud_adapter_list_directories_parses_depth_one_collections(monkeypatch) -> None:
    xml_body = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/files/nc-user/mdr/archive/</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype><d:collection/></d:resourcetype>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/nc-user/mdr/archive/2026/</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype><d:collection/></d:resourcetype>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/nc-user/mdr/archive/reports/</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype><d:collection/></d:resourcetype>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/nc-user/mdr/archive/readme.txt</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype />
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>
"""

    def _fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        assert method == "PROPFIND"
        assert kwargs.get("headers", {}).get("Depth") == "1"
        return _FakeResponse(207, xml_body)

    monkeypatch.setattr(requests, "request", _fake_request)
    adapter = NextcloudAdapter(
        base_url="https://nextcloud.example.com",
        username="nc-user",
        app_password="secret",
        root_path="/mdr",
    )
    payload = adapter.list_directories("/archive")
    assert payload.get("current_path") == "/archive"
    folders = payload.get("folders") or []
    assert folders == [
        {"name": "2026", "path": "/archive/2026"},
        {"name": "reports", "path": "/archive/reports"},
    ]


def test_nextcloud_adapter_list_directories_rejects_path_traversal() -> None:
    adapter = NextcloudAdapter(
        base_url="https://nextcloud.example.com",
        username="nc-user",
        app_password="secret",
        root_path="/mdr",
    )
    try:
        adapter.list_directories("/archive/../secret")
    except ValueError as exc:
        assert "traversal" in str(exc).lower()
    else:
        raise AssertionError("Expected traversal to raise ValueError")


def test_nextcloud_adapter_create_public_share_uses_resolved_path(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def _fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"method": method, "url": url, **kwargs})
        return _FakeResponse(
            200,
            json_payload={
                "ocs": {
                    "meta": {"statuscode": 100, "message": "OK"},
                    "data": {
                        "id": "42",
                        "token": "public-token",
                        "url": "https://nextcloud.example.com/s/public-token",
                        "path": "/archive/TSEED/file.pdf",
                    },
                }
            },
        )

    monkeypatch.setattr(requests, "request", _fake_request)
    adapter = NextcloudAdapter(
        base_url="https://nextcloud.example.com",
        username="nc-user",
        app_password="secret",
    )

    result = adapter.create_public_share(
        remote_relative_path="/archive/TSEED/file.pdf",
        password="Secret-123",
        expire_date="2026-07-06",
        permissions=1,
    )

    assert result["provider_share_id"] == "42"
    assert result["url"] == "https://nextcloud.example.com/s/public-token"
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "https://nextcloud.example.com/ocs/v2.php/apps/files_sharing/api/v1/shares"
    assert calls[0]["headers"]["OCS-APIRequest"] == "true"
    assert calls[0]["params"]["format"] == "json"
    assert calls[0]["data"]["path"] == "/archive/TSEED/file.pdf"
    assert calls[0]["data"]["shareType"] == 3
    assert calls[0]["data"]["permissions"] == 1
    assert calls[0]["data"]["password"] == "Secret-123"
    assert calls[0]["data"]["expireDate"] == "2026-07-06"


def test_nextcloud_adapter_create_public_share_omits_blank_password(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def _fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"method": method, "url": url, **kwargs})
        return _FakeResponse(
            200,
            json_payload={
                "ocs": {
                    "meta": {"statuscode": 100, "message": "OK"},
                    "data": {
                        "id": "43",
                        "token": "public-token",
                        "url": "https://nextcloud.example.com/s/public-token",
                    },
                }
            },
        )

    monkeypatch.setattr(requests, "request", _fake_request)
    adapter = NextcloudAdapter(
        base_url="https://nextcloud.example.com",
        username="nc-user",
        app_password="secret",
    )

    adapter.create_public_share(
        remote_relative_path="/archive/TSEED/no-password.pdf",
        password=None,
        permissions=1,
    )

    assert calls[0]["data"]["path"] == "/archive/TSEED/no-password.pdf"
    assert calls[0]["data"]["permissions"] == 1
    assert "password" not in calls[0]["data"]


def test_nextcloud_adapter_delete_share_uses_provider_share_id(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def _fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"method": method, "url": url, **kwargs})
        return _FakeResponse(
            200,
            json_payload={"ocs": {"meta": {"statuscode": 100, "message": "OK"}, "data": []}},
        )

    monkeypatch.setattr(requests, "request", _fake_request)
    adapter = NextcloudAdapter(
        base_url="https://nextcloud.example.com/nextcloud",
        username="nc-user",
        app_password="secret",
    )

    assert adapter.delete_share("42") is True
    assert calls[0]["method"] == "DELETE"
    assert calls[0]["url"] == "https://nextcloud.example.com/nextcloud/ocs/v2.php/apps/files_sharing/api/v1/shares/42"
    assert calls[0]["headers"]["OCS-APIRequest"] == "true"
