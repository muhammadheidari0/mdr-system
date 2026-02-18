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
        assert "default_project_id" not in openproject

        nav_res = client.get("/api/v1/settings/storage-integrations", headers=headers)
        assert nav_res.status_code == 200, nav_res.text
        nav_body = nav_res.json()
        nav_openproject = nav_body.get("integrations", {}).get("openproject", {})
        assert nav_openproject.get("token_source") == "settings"
        assert nav_openproject.get("api_token_configured") is True
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
