from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.services.storage_policy import get_storage_integrations, set_storage_integrations
from tests.auth_helpers import get_auth_headers

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _read_integrations_raw() -> dict:
    with SessionLocal() as db:
        return get_storage_integrations(db)


def _restore_integrations_raw(payload: dict) -> None:
    with SessionLocal() as db:
        set_storage_integrations(db, payload)
        db.commit()


def test_storage_integrations_token_source_and_redaction(monkeypatch) -> None:
    headers = _admin_headers()
    before = _read_integrations_raw()
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "")

    token_value = "settings-token-xyz"
    try:
        save_res = client.post(
            "/api/v1/settings/storage-integrations",
            json={
                "openproject": {
                    "enabled": True,
                    "base_url": "https://open-project.example.com/api/v3",
                    "api_token": token_value,
                    "default_work_package_id": "321",
                    "skip_ssl_verify": True,
                }
            },
            headers=headers,
        )
        assert save_res.status_code == 200, save_res.text
        save_body = save_res.json()
        openproject = save_body.get("integrations", {}).get("openproject", {})
        assert "api_token" not in openproject
        assert openproject.get("token_source") == "settings"
        assert openproject.get("api_token_configured") is True
        assert str(openproject.get("default_work_package_id") or "") == "321"
        assert openproject.get("skip_ssl_verify") is True
        assert openproject.get("ssl_source") == "settings"
        assert openproject.get("ssl_force_active") is False
        assert "default_project_id" not in openproject

        nav_res = client.get("/api/v1/settings/storage-integrations", headers=headers)
        assert nav_res.status_code == 200, nav_res.text
        nav_body = nav_res.json()
        nav_openproject = nav_body.get("integrations", {}).get("openproject", {})
        assert nav_openproject.get("token_source") == "settings"
        assert nav_openproject.get("api_token_configured") is True
        assert nav_openproject.get("skip_ssl_verify") is True
        assert nav_openproject.get("ssl_source") == "settings"
        assert nav_openproject.get("ssl_force_active") is False
        assert "api_token" not in nav_openproject

        audit_res = client.get(
            "/api/v1/settings/audit-logs?action=storage_integrations.update&page_size=1",
            headers=headers,
        )
        assert audit_res.status_code == 200, audit_res.text
        items = audit_res.json().get("items", [])
        assert items
        row = items[0]
        assert token_value not in str(row.get("before_json") or "")
        assert token_value not in str(row.get("after_json") or "")
    finally:
        _restore_integrations_raw(before)


def test_storage_integrations_env_precedence_and_clear(monkeypatch) -> None:
    headers = _admin_headers()
    before = _read_integrations_raw()
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "env-token-abc")
    try:
        save_res = client.post(
            "/api/v1/settings/storage-integrations",
            json={"openproject": {"enabled": True, "api_token": "settings-token-should-not-win"}},
            headers=headers,
        )
        assert save_res.status_code == 200, save_res.text
        save_openproject = save_res.json().get("integrations", {}).get("openproject", {})
        assert save_openproject.get("token_source") == "env"
        assert save_openproject.get("api_token_configured") is True

        clear_res = client.post(
            "/api/v1/settings/storage-integrations/openproject/clear-token",
            headers=headers,
        )
        assert clear_res.status_code == 200, clear_res.text
        clear_openproject = clear_res.json().get("integrations", {}).get("openproject", {})
        assert clear_openproject.get("token_source") == "env"
        assert clear_openproject.get("api_token_configured") is True

        monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "")
        clear_again_res = client.post(
            "/api/v1/settings/storage-integrations/openproject/clear-token",
            headers=headers,
        )
        assert clear_again_res.status_code == 200, clear_again_res.text
        clear_again_openproject = clear_again_res.json().get("integrations", {}).get("openproject", {})
        assert clear_again_openproject.get("token_source") == "none"
        assert clear_again_openproject.get("api_token_configured") is False
    finally:
        _restore_integrations_raw(before)


def test_storage_integrations_ssl_force_metadata(monkeypatch) -> None:
    headers = _admin_headers()
    before = _read_integrations_raw()
    monkeypatch.setattr(settings, "OPENPROJECT_API_TOKEN", "")
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "false")
    try:
        save_res = client.post(
            "/api/v1/settings/storage-integrations",
            json={
                "openproject": {
                    "enabled": True,
                    "skip_ssl_verify": False,
                }
            },
            headers=headers,
        )
        assert save_res.status_code == 200, save_res.text
        openproject = save_res.json().get("integrations", {}).get("openproject", {})
        assert openproject.get("ssl_force_active") is True
        assert openproject.get("ssl_source") == "env_force"
        assert openproject.get("skip_ssl_verify") is True
    finally:
        _restore_integrations_raw(before)


def test_storage_integrations_google_oauth_fields_and_redaction() -> None:
    headers = _admin_headers()
    before = _read_integrations_raw()
    google_secret = "google-secret-xyz"
    google_refresh = "google-refresh-xyz"
    try:
        save_res = client.post(
            "/api/v1/settings/storage-integrations",
            json={
                "google_drive": {
                    "enabled": True,
                    "drive_enabled": True,
                    "gmail_enabled": True,
                    "calendar_enabled": True,
                    "shared_drive_id": "shared-123",
                    "root_folder_id": "root-999",
                    "oauth_client_id": "client-id-1",
                    "oauth_client_secret": google_secret,
                    "oauth_refresh_token": google_refresh,
                    "sender_email": "sender@example.com",
                    "calendar_id": "calendar-1",
                }
            },
            headers=headers,
        )
        assert save_res.status_code == 200, save_res.text
        google = save_res.json().get("integrations", {}).get("google_drive", {})
        assert google.get("oauth_client_id") == "client-id-1"
        assert google.get("oauth_configured") is True
        assert "oauth_client_secret" not in google
        assert "oauth_refresh_token" not in google

        read_res = client.get("/api/v1/settings/storage-integrations", headers=headers)
        assert read_res.status_code == 200, read_res.text
        read_google = read_res.json().get("integrations", {}).get("google_drive", {})
        assert read_google.get("oauth_client_id") == "client-id-1"
        assert read_google.get("oauth_configured") is True
        assert "oauth_client_secret" not in read_google
        assert "oauth_refresh_token" not in read_google

        preserve_res = client.post(
            "/api/v1/settings/storage-integrations",
            json={
                "google_drive": {
                    "oauth_client_secret": "",
                    "oauth_refresh_token": "",
                }
            },
            headers=headers,
        )
        assert preserve_res.status_code == 200, preserve_res.text
        preserve_google = preserve_res.json().get("integrations", {}).get("google_drive", {})
        assert preserve_google.get("oauth_configured") is True

        audit_res = client.get(
            "/api/v1/settings/audit-logs?action=storage_integrations.update&page_size=1",
            headers=headers,
        )
        assert audit_res.status_code == 200, audit_res.text
        row = (audit_res.json().get("items") or [])[0]
        assert google_secret not in str(row.get("before_json") or "")
        assert google_secret not in str(row.get("after_json") or "")
        assert google_refresh not in str(row.get("before_json") or "")
        assert google_refresh not in str(row.get("after_json") or "")
    finally:
        _restore_integrations_raw(before)


def test_storage_integrations_nextcloud_fields_redaction_and_password_preserve(monkeypatch) -> None:
    headers = _admin_headers()
    before = _read_integrations_raw()
    nextcloud_password = "nextcloud-app-password-xyz"
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "NEXTCLOUD_TLS_VERIFY_FORCE", "")
    try:
        save_res = client.post(
            "/api/v1/settings/storage-integrations",
            json={
                "mirror": {"provider": "nextcloud"},
                "nextcloud": {
                    "enabled": True,
                    "base_url": "https://nextcloud.example.com",
                    "username": "nc-user",
                    "app_password": nextcloud_password,
                    "root_path": "/mdr",
                    "skip_ssl_verify": True,
                },
            },
            headers=headers,
        )
        assert save_res.status_code == 200, save_res.text
        body = save_res.json()
        mirror = body.get("integrations", {}).get("mirror", {})
        nextcloud = body.get("integrations", {}).get("nextcloud", {})
        assert mirror.get("provider") == "nextcloud"
        assert nextcloud.get("enabled") is True
        assert nextcloud.get("base_url") == "https://nextcloud.example.com"
        assert nextcloud.get("username") == "nc-user"
        assert nextcloud.get("root_path") == "/mdr"
        assert nextcloud.get("credential_source") == "settings"
        assert nextcloud.get("credentials_configured") is True
        assert nextcloud.get("skip_ssl_verify") is True
        assert nextcloud.get("ssl_source") == "settings"
        assert nextcloud.get("ssl_force_active") is False
        assert "app_password" not in nextcloud

        read_res = client.get("/api/v1/settings/storage-integrations", headers=headers)
        assert read_res.status_code == 200, read_res.text
        read_nextcloud = read_res.json().get("integrations", {}).get("nextcloud", {})
        assert read_nextcloud.get("credential_source") == "settings"
        assert read_nextcloud.get("credentials_configured") is True
        assert "app_password" not in read_nextcloud

        preserve_res = client.post(
            "/api/v1/settings/storage-integrations",
            json={
                "nextcloud": {
                    "app_password": "",
                }
            },
            headers=headers,
        )
        assert preserve_res.status_code == 200, preserve_res.text
        preserve_nextcloud = preserve_res.json().get("integrations", {}).get("nextcloud", {})
        assert preserve_nextcloud.get("credential_source") == "settings"
        assert preserve_nextcloud.get("credentials_configured") is True

        invalid_provider_res = client.post(
            "/api/v1/settings/storage-integrations",
            json={"mirror": {"provider": "invalid-provider"}},
            headers=headers,
        )
        assert invalid_provider_res.status_code == 200, invalid_provider_res.text
        invalid_mirror = invalid_provider_res.json().get("integrations", {}).get("mirror", {})
        assert invalid_mirror.get("provider") == "none"

        audit_res = client.get(
            "/api/v1/settings/audit-logs?action=storage_integrations.update&page_size=5",
            headers=headers,
        )
        assert audit_res.status_code == 200, audit_res.text
        items = audit_res.json().get("items", [])
        assert items
        combined = " ".join(
            f"{item.get('before_json') or ''} {item.get('after_json') or ''}"
            for item in items
        )
        assert nextcloud_password not in combined
    finally:
        _restore_integrations_raw(before)
