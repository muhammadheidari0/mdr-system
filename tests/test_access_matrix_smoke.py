from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from tests.site_logs_helpers import (
    admin_headers,
    create_scoped_user_and_login,
    ensure_project_discipline,
)


client = TestClient(app)


def _get_matrix(admin: dict[str, str], category: str) -> dict[str, Any]:
    res = client.get(f"/api/v1/settings/permissions/matrix?category={category}", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    assert body.get("category") == category
    return body


def _save_matrix(admin: dict[str, str], category: str, matrix: dict[str, dict[str, bool]]) -> None:
    res = client.post(
        f"/api/v1/settings/permissions/matrix?category={category}",
        json={"matrix": matrix},
        headers=admin,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True


def _pick_permission(payload: dict[str, Any], candidates: list[str]) -> str:
    permissions = [str(item) for item in (payload.get("permissions") or [])]
    assert permissions, "permissions list is empty"
    for key in candidates:
        if key in permissions:
            return key
    return permissions[0]


def test_smoke_navigation_for_all_org_categories() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    expected_default_hub = {
        "consultant": "consultant",
        "contractor": "contractor",
        "employer": "reports",
        "dcc": "edms",
        "system": "dashboard",
    }

    nav_permissions = [
        "dashboard:read",
        "reports:read",
        "archive:read",
        "transmittal:read",
        "correspondence:read",
        "module_settings:read",
        "hub_edms:read",
        "hub_reports:read",
        "hub_contractor:read",
        "hub_consultant:read",
        "module_archive:read",
        "module_transmittal:read",
        "module_correspondence:read",
        "module_reports:read",
        "module_site_logs_contractor:read",
        "module_comm_items_contractor:read",
        "module_permit_qc_contractor:read",
        "module_site_logs_consultant:read",
        "module_comm_items_consultant:read",
        "module_permit_qc_consultant:read",
    ]

    original_by_category: dict[str, dict[str, dict[str, bool]]] = {}
    for category in expected_default_hub:
        payload = _get_matrix(admin, category)
        original = deepcopy(payload.get("matrix") or {})
        original_by_category[category] = original
        modified = deepcopy(original)
        modified.setdefault("user", {})
        available = set(str(item) for item in (payload.get("permissions") or []))
        for permission in nav_permissions:
            if permission in available:
                modified["user"][permission] = True
        _save_matrix(admin, category, modified)

    try:
        for org_type, default_hub in expected_default_hub.items():
            user = create_scoped_user_and_login(
                client,
                admin,
                org_type=org_type,
                project_code=project_code,
                discipline_code=discipline_code,
                email_prefix=f"smoke_nav_{org_type}_{uuid4().hex[:6]}",
            )
            headers = user["headers"]  # type: ignore[assignment]

            nav_res = client.get("/api/v1/auth/navigation", headers=headers)  # type: ignore[arg-type]
            assert nav_res.status_code == 200, nav_res.text
            body = nav_res.json()
            assert body.get("ok") is True
            assert body.get("category") == org_type

            hubs = body.get("hubs", {})
            modules = body.get("modules", {})
            assert isinstance(hubs, dict)
            assert isinstance(modules, dict)
            assert body.get("default_hub") == default_hub
            assert hubs.get(default_hub) is True

            # Keep legacy navigation fields stable until full UI migration.
            edms_tabs = body.get("edms_tabs", {})
            assert isinstance(edms_tabs, dict)
            assert body.get("default_edms_tab") in edms_tabs
    finally:
        for category, matrix in original_by_category.items():
            _save_matrix(admin, category, matrix)


def test_smoke_permissions_matrix_categories_and_system_enforcement() -> None:
    admin = admin_headers(client)
    categories = ["consultant", "contractor", "employer", "dcc", "system"]

    payload_by_category = {category: _get_matrix(admin, category) for category in categories}
    for category in categories:
        body = payload_by_category[category]
        assert category in (body.get("categories") or [])
        assert bool(body.get("read_only")) is (category == "system")
        assert isinstance(body.get("matrix"), dict)
        assert isinstance(body.get("roles"), list)
        assert isinstance(body.get("permissions"), list)

    # DCC matrix is editable and independent from consultant matrix.
    dcc_payload = payload_by_category["dcc"]
    consultant_payload = payload_by_category["consultant"]
    dcc_original = deepcopy(dcc_payload.get("matrix") or {})
    consultant_original = deepcopy(consultant_payload.get("matrix") or {})
    test_permission = _pick_permission(
        dcc_payload,
        ["module_reports:read", "reports:read", "module_archive:read", "archive:read"],
    )

    dcc_modified = deepcopy(dcc_original)
    dcc_modified.setdefault("user", {})
    current_value = bool(dcc_modified["user"].get(test_permission, False))
    dcc_modified["user"][test_permission] = not current_value

    try:
        _save_matrix(admin, "dcc", dcc_modified)

        dcc_after = _get_matrix(admin, "dcc")
        consultant_after = _get_matrix(admin, "consultant")
        assert bool(dcc_after["matrix"]["user"].get(test_permission, False)) is (not current_value)
        assert bool(consultant_after["matrix"]["user"].get(test_permission, False)) is bool(
            consultant_original.get("user", {}).get(test_permission, False)
        )
    finally:
        _save_matrix(admin, "dcc", dcc_original)

    # system category must remain full-access even after POST with false values.
    system_payload = _get_matrix(admin, "system")
    roles = [str(item) for item in (system_payload.get("roles") or [])]
    permissions = [str(item) for item in (system_payload.get("permissions") or [])]
    assert roles and permissions

    all_false_matrix = {role: {permission: False for permission in permissions} for role in roles}
    _save_matrix(admin, "system", all_false_matrix)

    system_after = _get_matrix(admin, "system")
    matrix_after = system_after.get("matrix", {})
    for role in roles:
        role_map = matrix_after.get(role, {})
        for permission in permissions:
            assert bool(role_map.get(permission, False)) is True


def test_smoke_endpoint_authorization_respects_permission_matrix_for_contractor(monkeypatch) -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    user = create_scoped_user_and_login(
        client,
        admin,
        org_type="contractor",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix=f"smoke_auth_contractor_{uuid4().hex[:6]}",
    )
    headers = user["headers"]  # type: ignore[assignment]

    monkeypatch.setattr(settings, "FEATURE_BIM_GATEWAY", True)

    contractor_payload = _get_matrix(admin, "contractor")
    contractor_original = deepcopy(contractor_payload.get("matrix") or {})
    available = set(str(item) for item in (contractor_payload.get("permissions") or []))
    target_permissions = ("workboard:read", "site_logs:read", "comm_items:read", "bim:read")
    can_toggle = [permission for permission in target_permissions if permission in available]
    assert can_toggle

    contractor_enabled = deepcopy(contractor_original)
    contractor_enabled.setdefault("user", {})
    for permission in can_toggle:
        contractor_enabled["user"][permission] = True
    _save_matrix(admin, "contractor", contractor_enabled)

    try:
        baseline_urls = [
            "/api/v1/workboard/catalog",
            "/api/v1/site-logs/catalog",
            "/api/v1/comm-items/catalog",
            "/api/v1/bim/config",
        ]
        for url in baseline_urls:
            res = client.get(url, headers=headers)  # type: ignore[arg-type]
            assert res.status_code == 200, f"{url} -> {res.status_code}: {res.text}"

        contractor_modified = deepcopy(contractor_enabled)
        contractor_modified.setdefault("user", {})
        for permission in can_toggle:
            contractor_modified["user"][permission] = False
        _save_matrix(admin, "contractor", contractor_modified)

        blocked_expectations = {
            "/api/v1/workboard/catalog": 403,
            "/api/v1/site-logs/catalog": 403,
            "/api/v1/comm-items/catalog": 403,
            "/api/v1/bim/config": 403,
        }
        for url, expected_status in blocked_expectations.items():
            res = client.get(url, headers=headers)  # type: ignore[arg-type]
            assert res.status_code == expected_status, f"{url} -> {res.status_code}: {res.text}"
    finally:
        _save_matrix(admin, "contractor", contractor_original)
