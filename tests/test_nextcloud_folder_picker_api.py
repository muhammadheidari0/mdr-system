from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.nextcloud_adapter import NextcloudAdapter
from tests.auth_helpers import get_auth_headers

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _patch_integrations(monkeypatch, **nextcloud: Any) -> None:
    payload = {
        "mirror": {"provider": "nextcloud"},
        "google_drive": {"enabled": False},
        "openproject": {"enabled": False},
        "nextcloud": {
            "enabled": True,
            "base_url": "https://nextcloud.example.com",
            "username": "nc-user",
            "app_password": "nc-pass",
            "root_path": "/mdr",
            "local_mount_root": "/mnt/nextcloud",
            **nextcloud,
        },
        "local_cache": {"enabled": True},
    }
    monkeypatch.setattr("app.api.v1.routers.storage.get_storage_integrations", lambda _db: payload)


def _patch_env_defaults(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEXTCLOUD_BASE_URL", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_ROOT_PATH", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_LOCAL_MOUNT_ROOT", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY_FORCE", "")


def test_nextcloud_folder_picker_success(monkeypatch) -> None:
    headers = _admin_headers()
    _patch_env_defaults(monkeypatch)
    _patch_integrations(monkeypatch)

    def _fake_list(self, path: str = "/"):
        assert path == "/archive"
        return {
            "current_path": "/archive",
            "folders": [
                {"name": "2026", "path": "/archive/2026"},
                {"name": "reports", "path": "/archive/reports"},
            ],
        }

    monkeypatch.setattr(NextcloudAdapter, "list_directories", _fake_list)
    res = client.post("/api/v1/storage/nextcloud/folders", headers=headers, json={"path": "/archive"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    assert body.get("current_path") == "/archive"
    assert body.get("current_local_path") == "/mnt/nextcloud/archive"
    assert body.get("local_mount_root_effective") == "/mnt/nextcloud"
    assert body.get("local_mount_root_source") == "settings"
    assert body.get("folders") == [
        {"name": "2026", "path": "/archive/2026", "local_path": "/mnt/nextcloud/archive/2026"},
        {"name": "reports", "path": "/archive/reports", "local_path": "/mnt/nextcloud/archive/reports"},
    ]


def test_nextcloud_folder_picker_requires_mount_root(monkeypatch) -> None:
    headers = _admin_headers()
    _patch_env_defaults(monkeypatch)
    _patch_integrations(monkeypatch, local_mount_root="")

    res = client.post("/api/v1/storage/nextcloud/folders", headers=headers, json={"path": "/"})
    assert res.status_code == 400, res.text
    assert "NEXTCLOUD_LOCAL_MOUNT_ROOT" in str(res.json().get("detail") or "")


def test_nextcloud_folder_picker_requires_enabled_and_credentials(monkeypatch) -> None:
    headers = _admin_headers()
    _patch_env_defaults(monkeypatch)
    _patch_integrations(monkeypatch, enabled=False, username="", app_password="")

    res = client.post("/api/v1/storage/nextcloud/folders", headers=headers, json={"path": "/"})
    assert res.status_code == 400, res.text
    assert "disabled" in str(res.json().get("detail") or "").lower()


def test_nextcloud_folder_picker_requires_credentials(monkeypatch) -> None:
    headers = _admin_headers()
    _patch_env_defaults(monkeypatch)
    _patch_integrations(monkeypatch, enabled=True, username="", app_password="")

    res = client.post("/api/v1/storage/nextcloud/folders", headers=headers, json={"path": "/"})
    assert res.status_code == 400, res.text
    assert "username/app password" in str(res.json().get("detail") or "").lower()


def test_nextcloud_folder_picker_rejects_path_traversal(monkeypatch) -> None:
    headers = _admin_headers()
    _patch_env_defaults(monkeypatch)
    _patch_integrations(monkeypatch)

    res = client.post("/api/v1/storage/nextcloud/folders", headers=headers, json={"path": "/archive/../secret"})
    assert res.status_code == 400, res.text
    assert "traversal" in str(res.json().get("detail") or "").lower()
