from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.services.storage_policy import get_bim_revit_integration, set_bim_revit_integration
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _read_bim_revit_raw() -> dict:
    with SessionLocal() as db:
        return get_bim_revit_integration(db)


def _restore_bim_revit_raw(payload: dict) -> None:
    with SessionLocal() as db:
        set_bim_revit_integration(db, payload)
        db.commit()


def test_bim_revit_settings_save_get_and_redaction() -> None:
    headers = _admin_headers()
    before = _read_bim_revit_raw()
    secret = "bim-secret-for-tests-123"
    try:
        save_res = client.post(
            "/api/v1/settings/bim-revit",
            json={
                "enabled": True,
                "require_plugin_signature": True,
                "api_endpoint_url": "https://mdr.example.com/api/v1/bim/edms/inbox/publish-batch",
                "plugin_key_id": "BIM-TEST-KEY",
                "plugin_secret": secret,
                "allowed_mime": ["application/pdf", "application/x-dwg"],
                "max_batch_size": 150,
            },
            headers=headers,
        )
        assert save_res.status_code == 200, save_res.text
        save_body = save_res.json()
        settings_payload = save_body.get("settings", {})
        assert settings_payload.get("enabled") is True
        assert settings_payload.get("require_plugin_signature") is True
        assert settings_payload.get("plugin_key_id") == "BIM-TEST-KEY"
        assert settings_payload.get("has_secret") is True
        assert "plugin_secret_encrypted" not in settings_payload
        assert "plugin_secret" not in settings_payload

        read_res = client.get("/api/v1/settings/bim-revit", headers=headers)
        assert read_res.status_code == 200, read_res.text
        read_settings = read_res.json().get("settings", {})
        assert read_settings.get("plugin_key_id") == "BIM-TEST-KEY"
        assert read_settings.get("has_secret") is True
        assert "plugin_secret_encrypted" not in read_settings
        assert "plugin_secret" not in read_settings

        raw = _read_bim_revit_raw()
        encrypted = str(raw.get("plugin_secret_encrypted") or "")
        assert encrypted
        assert encrypted != secret
    finally:
        _restore_bim_revit_raw(before)


def test_bim_revit_settings_rotate_secret_returns_one_time_secret() -> None:
    headers = _admin_headers()
    before = _read_bim_revit_raw()
    try:
        save_res = client.post(
            "/api/v1/settings/bim-revit",
            json={
                "enabled": True,
                "require_plugin_signature": True,
                "api_endpoint_url": "https://mdr.example.com/api/v1/bim/edms/inbox/publish-batch",
                "plugin_key_id": "BIM-ROTATE-KEY",
                "plugin_secret": "initial-secret-xyz",
            },
            headers=headers,
        )
        assert save_res.status_code == 200, save_res.text

        rotate_res = client.post("/api/v1/settings/bim-revit/rotate-secret", headers=headers)
        assert rotate_res.status_code == 200, rotate_res.text
        rotate_body = rotate_res.json()
        assert rotate_body.get("ok") is True
        assert rotate_body.get("plugin_key_id") == "BIM-ROTATE-KEY"
        one_time_secret = str(rotate_body.get("plugin_secret") or "")
        assert one_time_secret

        read_res = client.get("/api/v1/settings/bim-revit", headers=headers)
        assert read_res.status_code == 200, read_res.text
        read_settings = read_res.json().get("settings", {})
        assert read_settings.get("has_secret") is True
        assert "plugin_secret" not in read_settings
    finally:
        _restore_bim_revit_raw(before)


def test_bim_revit_settings_require_admin() -> None:
    res = client.get("/api/v1/settings/bim-revit")
    assert res.status_code in (401, 403), res.text

