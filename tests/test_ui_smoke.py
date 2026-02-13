from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def test_ui_smoke_public_pages_load() -> None:
    home = client.get("/")
    assert home.status_code == 200, home.text
    assert 'id="view-dashboard"' in home.text

    login = client.get("/login")
    assert login.status_code == 200, login.text

    debug_login = client.get("/debug_login")
    assert debug_login.status_code == 200, debug_login.text

    docs = client.get("/docs")
    assert docs.status_code == 200, docs.text


def test_ui_smoke_whitelisted_partials_load() -> None:
    expected_markers = {
        "dashboard": 'id="view-dashboard"',
        "edms": 'id="view-edms"',
        "reports": 'id="view-reports"',
        "contractor": 'id="view-contractor"',
        "consultant": 'id="view-consultant"',
        "profile": 'id="view-profile"',
        "settings": 'id="view-settings"',
    }

    for partial, marker in expected_markers.items():
        response = client.get(f"/ui/partial/{partial}")
        assert response.status_code == 200, f"{partial}: {response.text}"
        assert marker in response.text, f"{partial}: expected marker `{marker}`"


def test_ui_smoke_priority_a_templates_have_no_inline_scripts_or_handlers() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    template_paths = [
        base_dir / "templates" / "base.html",
        base_dir / "templates" / "views" / "archive.html",
        base_dir / "templates" / "views" / "partials" / "settings_users_tab.html",
        base_dir / "templates" / "views" / "profile_settings.html",
        base_dir / "templates" / "components" / "doc_search.html",
        base_dir / "templates" / "views" / "edms.html",
        base_dir / "templates" / "views" / "transmittal.html",
        base_dir / "templates" / "views" / "correspondence.html",
        base_dir / "templates" / "views" / "contractor_hub.html",
        base_dir / "templates" / "views" / "consultant_hub.html",
        base_dir / "templates" / "views" / "partials" / "settings_bulk_tab.html",
        base_dir / "templates" / "mdr" / "bulk_register.html",
        base_dir / "templates" / "login_standalone.html",
        base_dir / "templates" / "views" / "debug_login.html",
    ]

    inline_script_pattern = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)
    inline_handler_pattern = re.compile(r"\bon[a-z]+\s*=", re.IGNORECASE)

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert inline_script_pattern.search(content) is None, f"Inline <script> found in {path}"
        assert inline_handler_pattern.search(content) is None, f"Inline handler found in {path}"


def test_ui_smoke_settings_storage_paths_roundtrip() -> None:
    headers = _admin_headers()

    before_res = client.get("/api/v1/settings/storage-paths", headers=headers)
    assert before_res.status_code == 200, before_res.text
    before = before_res.json()
    assert before.get("ok") is True

    payload = {
        "mdr_storage_path": f"./files/ui_smoke_technical_{uuid.uuid4().hex[:8]}",
        "correspondence_storage_path": f"./files/ui_smoke_correspondence_{uuid.uuid4().hex[:8]}",
    }

    try:
        save_res = client.post("/api/v1/settings/storage-paths", json=payload, headers=headers)
        assert save_res.status_code == 200, save_res.text
        save_body = save_res.json()
        assert save_body.get("ok") is True
        assert save_body.get("mdr_storage_path") == payload["mdr_storage_path"]
        assert save_body.get("correspondence_storage_path") == payload["correspondence_storage_path"]
    finally:
        restore_payload = {
            "mdr_storage_path": before.get("mdr_storage_path") or "./files/technical",
            "correspondence_storage_path": before.get("correspondence_storage_path") or "./files/correspondence",
        }
        restore_res = client.post("/api/v1/settings/storage-paths", json=restore_payload, headers=headers)
        assert restore_res.status_code == 200, restore_res.text


def test_ui_smoke_workboard_crud_flow() -> None:
    headers = _admin_headers()

    create_payload = {
        "module_key": "contractor",
        "tab_key": "execution",
        "title": f"UI smoke {uuid.uuid4().hex[:6]}",
        "description": "created by ui smoke",
        "status": "open",
        "priority": "normal",
    }

    create_res = client.post("/api/v1/workboard/create", json=create_payload, headers=headers)
    assert create_res.status_code == 200, create_res.text
    create_body = create_res.json()
    assert create_body.get("ok") is True
    item_id = int(create_body.get("data", {}).get("id"))

    try:
        list_res = client.get(
            "/api/v1/workboard/list?module_key=contractor&tab_key=execution&skip=0&limit=20",
            headers=headers,
        )
        assert list_res.status_code == 200, list_res.text
        list_body = list_res.json()
        assert list_body.get("ok") is True
        assert any(int(row.get("id", 0)) == item_id for row in list_body.get("data", []))

        update_res = client.put(
            f"/api/v1/workboard/{item_id}",
            json={"status": "done", "priority": "high"},
            headers=headers,
        )
        assert update_res.status_code == 200, update_res.text
        update_body = update_res.json()
        assert update_body.get("ok") is True
        assert update_body.get("data", {}).get("status") == "done"
    finally:
        delete_res = client.delete(f"/api/v1/workboard/{item_id}", headers=headers)
        assert delete_res.status_code == 200, delete_res.text


def test_ui_smoke_archive_endpoints_with_auth() -> None:
    headers = _admin_headers()

    form_res = client.get("/api/v1/archive/form-data", headers=headers)
    assert form_res.status_code == 200, form_res.text
    form_body = form_res.json()
    assert isinstance(form_body.get("projects"), list)
    assert isinstance(form_body.get("disciplines"), list)

    list_res = client.get("/api/v1/archive/list?skip=0&limit=10", headers=headers)
    assert list_res.status_code == 200, list_res.text
    list_body = list_res.json()
    assert list_body.get("ok") is True
    assert "data" in list_body
    assert isinstance(list_body.get("data"), list)

    bulk_page_res = client.get("/api/v1/mdr/bulk-register-page")
    assert bulk_page_res.status_code == 200, bulk_page_res.text
    assert "bulkRegisterFrame" not in bulk_page_res.text
    assert "tableBody" in bulk_page_res.text


def test_ui_smoke_transmittal_and_correspondence_endpoints_with_auth() -> None:
    headers = _admin_headers()

    tr_stats_res = client.get("/api/v1/transmittal/stats/summary", headers=headers)
    assert tr_stats_res.status_code == 200, tr_stats_res.text
    tr_stats = tr_stats_res.json()
    assert "total_transmittals" in tr_stats

    tr_list_res = client.get("/api/v1/transmittal/", headers=headers)
    assert tr_list_res.status_code == 200, tr_list_res.text
    assert isinstance(tr_list_res.json(), list)

    corr_catalog_res = client.get("/api/v1/correspondence/catalog", headers=headers)
    assert corr_catalog_res.status_code == 200, corr_catalog_res.text
    corr_catalog = corr_catalog_res.json()
    assert corr_catalog.get("ok") is True
    assert isinstance(corr_catalog.get("issuing_entities"), list)
    assert isinstance(corr_catalog.get("categories"), list)

    corr_dashboard_res = client.get("/api/v1/correspondence/dashboard", headers=headers)
    assert corr_dashboard_res.status_code == 200, corr_dashboard_res.text
    corr_dashboard = corr_dashboard_res.json()
    assert corr_dashboard.get("ok") is True
    assert isinstance(corr_dashboard.get("stats"), dict)

    corr_list_res = client.get("/api/v1/correspondence/list?skip=0&limit=10", headers=headers)
    assert corr_list_res.status_code == 200, corr_list_res.text
    corr_list = corr_list_res.json()
    assert corr_list.get("ok") is True
    assert isinstance(corr_list.get("data"), list)
