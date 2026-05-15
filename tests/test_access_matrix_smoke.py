from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.access_matrix import build_navigation_diagnostics, build_navigation_state
from app.core.permission_catalog import permission_keys
from app.db.models import RoleCategoryPermission
from app.db.session import SessionLocal
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


def _get_scope(admin: dict[str, str], category: str) -> dict[str, Any]:
    res = client.get(f"/api/v1/settings/permissions/scope?category={category}", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    assert body.get("category") == category
    return body


def test_smoke_navigation_for_all_org_categories() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    expected_default_hub = {
        "consultant": "consultant",
        "contractor": "contractor",
        "employer": "reports",
        "dcc": "edms",
    }

    nav_permissions = [
        "dashboard:read",
        "reports:read",
        "archive:read",
        "transmittal:read",
        "correspondence:read",
        "module_settings_edms:read",
        "module_settings_contractor:read",
        "module_settings_consultant:read",
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
        admin_nav_res = client.get("/api/v1/auth/navigation", headers=admin)
        assert admin_nav_res.status_code == 200, admin_nav_res.text
        admin_nav = admin_nav_res.json()
        assert admin_nav.get("ok") is True
        assert admin_nav.get("is_system_admin") is True
        assert admin_nav.get("permission_category") == "system"
        assert admin_nav.get("default_hub") == "dashboard"
    finally:
        for category, matrix in original_by_category.items():
            _save_matrix(admin, category, matrix)


def test_smoke_permissions_matrix_categories_and_roles() -> None:
    admin = admin_headers(client)
    categories = ["consultant", "contractor", "employer", "dcc"]

    payload_by_category = {category: _get_matrix(admin, category) for category in categories}
    for category in categories:
        body = payload_by_category[category]
        assert category in (body.get("categories") or [])
        assert "system" not in (body.get("categories") or [])
        assert bool(body.get("read_only")) is False
        assert isinstance(body.get("matrix"), dict)
        assert isinstance(body.get("roles"), list)
        assert isinstance(body.get("permissions"), list)
        assert isinstance(body.get("permissions_meta"), list)
        assert isinstance(body.get("feature_catalog"), list)
        assert isinstance(body.get("baseline_matrix"), dict)
        assert isinstance(body.get("role_labels"), dict)
        assert isinstance(body.get("category_label"), str)
        roles = [str(item) for item in (body.get("roles") or [])]
        assert "admin" not in roles
        assert set(roles).issubset({"manager", "dcc", "project_control", "user", "viewer"})
        assert "project_control" in roles
        expected_keys = set(str(item) for item in (body.get("permissions") or []))
        for role in roles:
            assert set((body.get("matrix") or {}).get(role, {}).keys()) == expected_keys
            assert set((body.get("baseline_matrix") or {}).get(role, {}).keys()) == expected_keys

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


def test_matrix_row_coverage_matches_canonical_permission_count() -> None:
    admin = admin_headers(client)
    for category in ("consultant", "contractor", "employer", "dcc"):
        payload = _get_matrix(admin, category)
        _save_matrix(admin, category, deepcopy(payload.get("matrix") or {}))

    canonical_permissions = set(permission_keys())
    expected_count = len(canonical_permissions)
    with SessionLocal() as db:
        rows = db.query(
            RoleCategoryPermission.category,
            RoleCategoryPermission.role,
            RoleCategoryPermission.permission,
        ).all()
    counts: dict[tuple[str, str], int] = {}
    for category, role, permission in rows:
        key = (str(category or "").strip().lower(), str(role or "").strip().lower())
        if str(permission or "").strip() in canonical_permissions:
            counts[key] = counts.get(key, 0) + 1

    for category in ("consultant", "contractor", "employer", "dcc"):
        for role in ("manager", "dcc", "project_control", "user", "viewer"):
            assert counts.get((category, role), 0) == expected_count


def test_permissions_scope_endpoint_exposes_role_and_category_labels() -> None:
    admin = admin_headers(client)
    payload = _get_scope(admin, "consultant")
    assert payload.get("category_label") == "مشاور"
    assert payload.get("scope_read_only") is False
    assert isinstance(payload.get("role_labels"), dict)
    assert set((payload.get("role_labels") or {}).keys()) == {"manager", "dcc", "project_control", "user", "viewer"}
    assert (payload.get("role_labels") or {}).get("project_control") == "کنترل پروژه"
    assert isinstance(payload.get("projects"), list)
    assert isinstance(payload.get("disciplines"), list)


def test_navigation_hides_tabs_when_module_visibility_lacks_domain_read() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    consultant_payload = _get_matrix(admin, "consultant")
    contractor_payload = _get_matrix(admin, "contractor")
    consultant_original = deepcopy(consultant_payload.get("matrix") or {})
    contractor_original = deepcopy(contractor_payload.get("matrix") or {})

    consultant_modified = deepcopy(consultant_original)
    consultant_modified.setdefault("user", {})
    consultant_modified["user"]["hub_consultant:read"] = True
    consultant_modified["user"]["module_site_logs_consultant:read"] = True
    consultant_modified["user"]["site_logs:read"] = False
    consultant_modified["user"]["module_comm_items_consultant:read"] = True
    consultant_modified["user"]["comm_items:read"] = True
    consultant_modified["user"]["module_permit_qc_consultant:read"] = True
    consultant_modified["user"]["permit_qc:read"] = False

    contractor_modified = deepcopy(contractor_original)
    contractor_modified.setdefault("user", {})
    contractor_modified["user"]["hub_contractor:read"] = True
    contractor_modified["user"]["module_comm_items_contractor:read"] = True
    contractor_modified["user"]["comm_items:read"] = False
    contractor_modified["user"]["module_site_logs_contractor:read"] = True
    contractor_modified["user"]["site_logs:read"] = True

    _save_matrix(admin, "consultant", consultant_modified)
    _save_matrix(admin, "contractor", contractor_modified)

    try:
        consultant_user = create_scoped_user_and_login(
            client,
            admin,
            org_type="consultant",
            project_code=project_code,
            discipline_code=discipline_code,
            email_prefix=f"nav_consultant_{uuid4().hex[:6]}",
            role="user",
            organization_role="user",
        )
        contractor_user = create_scoped_user_and_login(
            client,
            admin,
            org_type="contractor",
            project_code=project_code,
            discipline_code=discipline_code,
            email_prefix=f"nav_contractor_{uuid4().hex[:6]}",
            role="user",
            organization_role="user",
        )

        consultant_nav = client.get("/api/v1/auth/navigation", headers=consultant_user["headers"])  # type: ignore[arg-type]
        assert consultant_nav.status_code == 200, consultant_nav.text
        consultant_body = consultant_nav.json()
        consultant_tabs = consultant_body.get("consultant_tabs", {})
        assert consultant_tabs.get("inspection") is False
        assert consultant_tabs.get("defects") is True
        assert consultant_tabs.get("instructions") is True
        assert consultant_tabs.get("control") is True
        assert consultant_tabs.get("permit_qc") is False

        contractor_nav = client.get("/api/v1/auth/navigation", headers=contractor_user["headers"])  # type: ignore[arg-type]
        assert contractor_nav.status_code == 200, contractor_nav.text
        contractor_body = contractor_nav.json()
        contractor_tabs = contractor_body.get("contractor_tabs", {})
        assert contractor_tabs.get("execution") is True
        assert contractor_tabs.get("requests") is False
    finally:
        _save_matrix(admin, "consultant", consultant_original)
        _save_matrix(admin, "contractor", contractor_original)


def test_navigation_etag_changes_when_matrix_changes() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    contractor_payload = _get_matrix(admin, "contractor")
    contractor_original = deepcopy(contractor_payload.get("matrix") or {})
    contractor_modified = deepcopy(contractor_original)
    contractor_modified.setdefault("user", {})
    contractor_modified["user"]["hub_contractor:read"] = True
    contractor_modified["user"]["module_site_logs_contractor:read"] = True
    contractor_modified["user"]["site_logs:read"] = True
    contractor_modified["user"]["module_comm_items_contractor:read"] = False
    contractor_modified["user"]["comm_items:read"] = False

    _save_matrix(admin, "contractor", contractor_modified)

    try:
        user = create_scoped_user_and_login(
            client,
            admin,
            org_type="contractor",
            project_code=project_code,
            discipline_code=discipline_code,
            email_prefix=f"nav_etag_{uuid4().hex[:6]}",
            role="user",
            organization_role="user",
        )
        headers = user["headers"]  # type: ignore[assignment]

        first = client.get("/api/v1/auth/navigation", headers=headers)  # type: ignore[arg-type]
        assert first.status_code == 200, first.text
        first_etag = first.headers.get("etag")
        assert first_etag

        contractor_modified["user"]["module_comm_items_contractor:read"] = True
        contractor_modified["user"]["comm_items:read"] = True
        _save_matrix(admin, "contractor", contractor_modified)

        second = client.get(
            "/api/v1/auth/navigation",
            headers={**headers, "If-None-Match": first_etag},  # type: ignore[arg-type]
        )
        assert second.status_code == 200, second.text
        second_etag = second.headers.get("etag")
        assert second_etag
        assert second_etag != first_etag

        body = second.json()
        contractor_tabs = body.get("contractor_tabs", {})
        assert contractor_tabs.get("requests") is True
    finally:
        _save_matrix(admin, "contractor", contractor_original)


def test_navigation_diagnostics_flags_unexpected_cross_hub_visibility() -> None:
    capabilities = {permission: False for permission in permission_keys()}
    capabilities["dashboard:read"] = True
    capabilities["hub_contractor:read"] = True
    capabilities["module_site_logs_contractor:read"] = True
    capabilities["site_logs:read"] = True
    capabilities["hub_consultant:read"] = True
    capabilities["module_site_logs_consultant:read"] = True
    capabilities["site_logs:read"] = True

    navigation = build_navigation_state(
        capabilities,
        category="contractor",
        effective_role="user",
    )
    diagnostics = build_navigation_diagnostics(navigation, category="contractor")

    assert "consultant" in diagnostics["visible_hubs"]
    assert "consultant" in diagnostics["unexpected_visible_hubs"]
    assert "unexpected_visible_hub:consultant" in diagnostics["warnings"]


def test_navigation_splits_internal_settings_visibility_per_hub() -> None:
    capabilities = {permission: False for permission in permission_keys()}
    capabilities["settings:read"] = True
    capabilities["module_settings_edms:read"] = True
    capabilities["module_settings_contractor:read"] = False
    capabilities["module_settings_consultant:read"] = True

    navigation = build_navigation_state(
        capabilities,
        category="dcc",
        effective_role="manager",
    )
    visibility = navigation["module_settings_visibility"]

    assert visibility["edms"] is True
    assert visibility["contractor"] is False
    assert visibility["consultant"] is True
    assert navigation["modules"]["settings"]["module_settings"] is True


def test_navigation_api_smoke_splits_internal_settings_gears_per_hub() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)
    user = create_scoped_user_and_login(
        client,
        admin,
        org_type="dcc",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix=f"gear_split_{uuid4().hex[:6]}",
        role="user",
        organization_role="user",
    )
    headers = user["headers"]  # type: ignore[assignment]

    payload = _get_matrix(admin, "dcc")
    original = deepcopy(payload.get("matrix") or {})
    available = set(str(item) for item in (payload.get("permissions") or []))

    base_permissions = {
        "dashboard:read",
        "settings:read",
        "hub_edms:read",
        "module_archive:read",
        "archive:read",
        "hub_contractor:read",
        "module_site_logs_contractor:read",
        "hub_consultant:read",
        "module_site_logs_consultant:read",
        "site_logs:read",
    }
    setting_permissions = (
        "module_settings_edms:read",
        "module_settings_contractor:read",
        "module_settings_consultant:read",
    )

    working = deepcopy(original)
    working.setdefault("user", {})
    for permission in base_permissions:
        if permission in available:
            working["user"][permission] = True
    for permission in setting_permissions:
        if permission in available:
            working["user"][permission] = False

    scenarios = [
        ("module_settings_edms:read", {"edms": True, "contractor": False, "consultant": False}),
        ("module_settings_contractor:read", {"edms": False, "contractor": True, "consultant": False}),
        ("module_settings_consultant:read", {"edms": False, "contractor": False, "consultant": True}),
    ]

    try:
        for permission_key, expected_visibility in scenarios:
            scenario_matrix = deepcopy(working)
            if permission_key in available:
                scenario_matrix["user"][permission_key] = True
            _save_matrix(admin, "dcc", scenario_matrix)

            response = client.get("/api/v1/auth/navigation", headers=headers)
            assert response.status_code == 200, response.text
            body = response.json()
            visibility = body.get("module_settings_visibility") or {}

            assert visibility == expected_visibility
            assert bool(body.get("edms")) is expected_visibility["edms"]
            assert bool(body.get("contractor")) is expected_visibility["contractor"]
            assert bool(body.get("consultant")) is expected_visibility["consultant"]
    finally:
        _save_matrix(admin, "dcc", original)


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
        role="user",
        organization_role="user",
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
