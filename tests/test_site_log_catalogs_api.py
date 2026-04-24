from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.db.session import SessionLocal
from app.main import app
from tests.site_logs_helpers import (
    admin_headers,
    create_scoped_user_and_login,
    ensure_project_discipline,
)


client = TestClient(app)


def _assert_catalog_schema_ready() -> None:
    with SessionLocal() as db:
        inspector = inspect(db.bind)
        missing = [
            table_name
            for table_name in (
                "site_log_role_catalog",
                "site_log_equipment_catalog",
                "site_log_equipment_status_catalog",
            )
            if not inspector.has_table(table_name)
        ]
    assert not missing, (
        "Site-log catalog tables are missing in the active database. "
        "Apply migration 20260424_0021_site_log_catalogs before running this test. "
        f"Missing: {', '.join(missing)}"
    )


def _upsert_catalog_item(
    headers: dict[str, str],
    *,
    catalog_type: str,
    code: str,
    label: str,
    sort_order: int = 10,
    is_active: bool = True,
    item_id: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "catalog_type": catalog_type,
        "code": code,
        "label": label,
        "sort_order": sort_order,
        "is_active": is_active,
    }
    if item_id:
        payload["id"] = item_id
    response = client.post(
        "/api/v1/settings/site-log-catalogs/upsert",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True
    return body


def _create_legacy_draft(
    headers: dict[str, str],
    *,
    project_code: str,
    discipline_code: str,
    organization_id: int,
    role_label: str,
    equipment_label: str,
    claimed_status: str,
) -> int:
    payload = {
        "log_type": "DAILY",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "organization_id": int(organization_id),
        "log_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
        "weather": "CLEAR",
        "summary": f"Legacy site log {uuid4().hex[:8]}",
        "manpower_rows": [
            {
                "role_code": None,
                "role_label": role_label,
                "claimed_count": 2,
                "claimed_hours": 8.0,
                "sort_order": 0,
            }
        ],
        "equipment_rows": [
            {
                "equipment_code": None,
                "equipment_label": equipment_label,
                "claimed_status": claimed_status,
                "claimed_hours": 6.5,
                "sort_order": 0,
            }
        ],
        "activity_rows": [],
    }
    response = client.post("/api/v1/site-logs/create", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True
    return int(body.get("data", {}).get("id") or 0)


def test_site_log_catalogs_settings_crud_and_runtime_visibility() -> None:
    _assert_catalog_schema_ready()
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    viewer = create_scoped_user_and_login(
        client,
        admin,
        org_type="contractor",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix=f"site_log_catalog_viewer_{uuid4().hex[:6]}",
        organization_role="viewer",
    )
    viewer_headers = viewer["headers"]  # type: ignore[assignment]

    settings_response = client.get("/api/v1/settings/site-log-catalogs", headers=admin)
    assert settings_response.status_code == 200, settings_response.text
    settings_body = settings_response.json()
    assert settings_body.get("ok") is True
    assert set((settings_body.get("catalogs") or {}).keys()) == {"role", "equipment", "equipment_status"}
    assert set((settings_body.get("catalog_titles") or {}).keys()) == {"role", "equipment", "equipment_status"}

    blocked_settings_read = client.get("/api/v1/settings/site-log-catalogs", headers=viewer_headers)  # type: ignore[arg-type]
    assert blocked_settings_read.status_code == 403, blocked_settings_read.text

    sample_payload = {
        "catalog_type": "role",
        "code": f"VIEW{uuid4().hex[:4].upper()}",
        "label": "Blocked write",
        "sort_order": 10,
        "is_active": True,
    }
    blocked_upsert = client.post(
        "/api/v1/settings/site-log-catalogs/upsert",
        json=sample_payload,
        headers=viewer_headers,  # type: ignore[arg-type]
    )
    assert blocked_upsert.status_code == 403, blocked_upsert.text

    created_items: dict[str, dict[str, object]] = {}
    for catalog_type, label_prefix in (
        ("role", "Role"),
        ("equipment", "Equipment"),
        ("equipment_status", "Status"),
    ):
        code = f"{catalog_type[:3].upper()}{uuid4().hex[:6].upper()}"
        label = f"{label_prefix} {uuid4().hex[:6]}"
        body = _upsert_catalog_item(
            admin,
            catalog_type=catalog_type,
            code=code,
            label=label,
            sort_order=25,
        )
        item = body.get("item") or {}
        assert str(item.get("code") or "") == code
        assert str(item.get("label") or "") == label
        assert bool(item.get("is_active")) is True
        created_items[catalog_type] = dict(item)

    runtime_catalog = client.get("/api/v1/site-logs/catalog", headers=viewer_headers)  # type: ignore[arg-type]
    assert runtime_catalog.status_code == 200, runtime_catalog.text
    runtime_body = runtime_catalog.json()
    assert runtime_body.get("ok") is True

    runtime_role_codes = {str(item.get("code") or "") for item in (runtime_body.get("role_catalog") or [])}
    runtime_equipment_codes = {str(item.get("code") or "") for item in (runtime_body.get("equipment_catalog") or [])}
    runtime_status_codes = {
        str(item.get("code") or "")
        for item in (runtime_body.get("equipment_status_catalog") or [])
    }
    assert str(created_items["role"]["code"]) in runtime_role_codes
    assert str(created_items["equipment"]["code"]) in runtime_equipment_codes
    assert str(created_items["equipment_status"]["code"]) in runtime_status_codes

    updated_role_label = f"Role Updated {uuid4().hex[:6]}"
    updated_role = _upsert_catalog_item(
        admin,
        catalog_type="role",
        item_id=int(created_items["role"]["id"]),
        code=str(created_items["role"]["code"]),
        label=updated_role_label,
        sort_order=35,
    )
    assert str((updated_role.get("item") or {}).get("label") or "") == updated_role_label

    delete_response = client.post(
        "/api/v1/settings/site-log-catalogs/delete",
        json={
            "catalog_type": "equipment_status",
            "id": int(created_items["equipment_status"]["id"]),
        },
        headers=admin,
    )
    assert delete_response.status_code == 200, delete_response.text
    delete_body = delete_response.json()
    assert delete_body.get("ok") is True
    assert bool((delete_body.get("item") or {}).get("is_active")) is False

    blocked_delete = client.post(
        "/api/v1/settings/site-log-catalogs/delete",
        json={
            "catalog_type": "equipment_status",
            "id": int(created_items["equipment_status"]["id"]),
        },
        headers=viewer_headers,  # type: ignore[arg-type]
    )
    assert blocked_delete.status_code == 403, blocked_delete.text

    settings_after_delete = client.get("/api/v1/settings/site-log-catalogs", headers=admin)
    assert settings_after_delete.status_code == 200, settings_after_delete.text
    settings_after_delete_body = settings_after_delete.json()
    settings_status_items = settings_after_delete_body.get("catalogs", {}).get("equipment_status") or []
    deleted_row = next(
        (
            item
            for item in settings_status_items
            if int(item.get("id") or 0) == int(created_items["equipment_status"]["id"])
        ),
        None,
    )
    assert deleted_row is not None
    assert bool(deleted_row.get("is_active")) is False

    runtime_after_delete = client.get("/api/v1/site-logs/catalog", headers=viewer_headers)  # type: ignore[arg-type]
    assert runtime_after_delete.status_code == 200, runtime_after_delete.text
    runtime_after_delete_body = runtime_after_delete.json()
    runtime_status_codes_after = {
        str(item.get("code") or "")
        for item in (runtime_after_delete_body.get("equipment_status_catalog") or [])
    }
    assert str(created_items["equipment_status"]["code"]) not in runtime_status_codes_after


def test_site_log_catalogs_preserve_legacy_free_text_rows() -> None:
    _assert_catalog_schema_ready()
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    contractor = create_scoped_user_and_login(
        client,
        admin,
        org_type="contractor",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix=f"site_log_catalog_editor_{uuid4().hex[:6]}",
        organization_role="user",
    )
    contractor_headers = contractor["headers"]  # type: ignore[assignment]

    legacy_role_label = f"Legacy Role {uuid4().hex[:6]}"
    legacy_equipment_label = f"Legacy Equipment {uuid4().hex[:6]}"
    legacy_status = f"legacy_status_{uuid4().hex[:4]}"

    draft_id = _create_legacy_draft(
        contractor_headers,  # type: ignore[arg-type]
        project_code=project_code,
        discipline_code=discipline_code,
        organization_id=int(contractor.get("organization_id") or 0),
        role_label=legacy_role_label,
        equipment_label=legacy_equipment_label,
        claimed_status=legacy_status,
    )
    assert draft_id > 0

    get_response = client.get(f"/api/v1/site-logs/{draft_id}", headers=contractor_headers)  # type: ignore[arg-type]
    assert get_response.status_code == 200, get_response.text
    get_body = get_response.json()
    assert get_body.get("ok") is True
    data = get_body.get("data") or {}

    manpower_rows = data.get("manpower_rows") or []
    equipment_rows = data.get("equipment_rows") or []
    assert manpower_rows
    assert equipment_rows
    assert str(manpower_rows[0].get("role_label") or "") == legacy_role_label
    assert str(equipment_rows[0].get("equipment_label") or "") == legacy_equipment_label
    assert str(equipment_rows[0].get("claimed_status") or "") == legacy_status.upper()

    update_response = client.put(
        f"/api/v1/site-logs/{draft_id}",
        json={
            "summary": f"Legacy updated {uuid4().hex[:6]}",
            "manpower_rows": manpower_rows,
            "equipment_rows": equipment_rows,
            "activity_rows": data.get("activity_rows") or [],
        },
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert update_response.status_code == 200, update_response.text
    update_body = update_response.json()
    assert update_body.get("ok") is True
    updated_data = update_body.get("data") or {}
    updated_manpower = updated_data.get("manpower_rows") or []
    updated_equipment = updated_data.get("equipment_rows") or []
    assert updated_manpower
    assert updated_equipment
    assert str(updated_manpower[0].get("role_label") or "") == legacy_role_label
    assert str(updated_equipment[0].get("equipment_label") or "") == legacy_equipment_label
    assert str(updated_equipment[0].get("claimed_status") or "") == legacy_status.upper()
