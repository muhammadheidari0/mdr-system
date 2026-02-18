from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from app.main import app
from tests.site_logs_helpers import (
    admin_headers,
    create_scoped_user_and_login,
    ensure_project_discipline,
)


client = TestClient(app)


def test_correspondence_permission_matrix_controls_navigation_and_catalog_access() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    consultant_user = create_scoped_user_and_login(
        client,
        admin,
        org_type="consultant",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="corr_consultant",
    )
    consultant_headers = consultant_user["headers"]  # type: ignore[assignment]

    matrix_res = client.get("/api/v1/settings/permissions/matrix?category=consultant", headers=admin)
    assert matrix_res.status_code == 200, matrix_res.text
    matrix_body = matrix_res.json()
    assert matrix_body.get("ok") is True

    permissions = matrix_body.get("permissions", [])
    assert "correspondence:read" in permissions

    matrix = matrix_body.get("matrix", {})
    assert isinstance(matrix, dict)
    assert isinstance(matrix.get("user"), dict)

    original_matrix = deepcopy(matrix)
    modified_matrix = deepcopy(matrix)
    modified_matrix.setdefault("user", {})
    modified_matrix["user"]["correspondence:read"] = False

    try:
        save_res = client.post(
            "/api/v1/settings/permissions/matrix?category=consultant",
            json={"matrix": modified_matrix},
            headers=admin,
        )
        assert save_res.status_code == 200, save_res.text
        save_body = save_res.json()
        assert save_body.get("ok") is True

        nav_res = client.get("/api/v1/auth/navigation", headers=consultant_headers)  # type: ignore[arg-type]
        assert nav_res.status_code == 200, nav_res.text
        nav_body = nav_res.json()
        assert nav_body.get("ok") is True
        tabs = nav_body.get("edms_tabs", {})
        assert tabs.get("correspondence") is False

        catalog_res = client.get("/api/v1/correspondence/catalog", headers=consultant_headers)  # type: ignore[arg-type]
        assert catalog_res.status_code == 403, catalog_res.text
    finally:
        restore_res = client.post(
            "/api/v1/settings/permissions/matrix?category=consultant",
            json={"matrix": original_matrix},
            headers=admin,
        )
        assert restore_res.status_code == 200, restore_res.text
