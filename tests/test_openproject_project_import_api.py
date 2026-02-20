from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.models import OpenProjectImportRun
from app.db.session import SessionLocal
from app.main import app
from app.services.openproject_adapter import OpenProjectAdapter
from app.services.storage_policy import get_storage_integrations, set_storage_integrations
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _read_integrations() -> dict:
    with SessionLocal() as db:
        return get_storage_integrations(db)


def _write_integrations(payload: dict) -> None:
    with SessionLocal() as db:
        set_storage_integrations(db, payload)
        db.commit()


def _delete_import_run(run_id: int) -> None:
    with SessionLocal() as db:
        db.query(OpenProjectImportRun).filter(OpenProjectImportRun.id == int(run_id)).delete()
        db.commit()


def test_openproject_project_preview_and_snapshot_import(monkeypatch) -> None:
    headers = _admin_headers()
    before_integrations = _read_integrations()
    run_id = 0

    preview_items = [
        {
            "id": 1001,
            "subject": "WP one",
            "startDate": "2026-02-01",
            "dueDate": "2026-02-10",
            "doneRatio": 30,
            "updatedAt": "2026-02-20T10:00:00Z",
            "_links": {
                "self": {"href": "/api/v3/work_packages/1001"},
                "status": {"title": "In progress"},
                "type": {"title": "Task"},
                "assignee": {"title": "John Doe"},
            },
        },
        {
            "id": 1002,
            "subject": "WP two",
            "startDate": "2026-02-11",
            "dueDate": "2026-02-20",
            "doneRatio": 80,
            "updatedAt": "2026-02-20T11:00:00Z",
            "_links": {
                "self": {"href": "/api/v3/work_packages/1002"},
                "status": {"title": "Closed"},
                "type": {"title": "Milestone"},
                "assignee": {"title": "Jane Doe"},
            },
        },
    ]

    def _fake_get_project(self, project_ref):
        return {
            "id": 7,
            "identifier": str(project_ref),
            "name": "Project T202",
            "_links": {"self": {"href": "/api/v3/projects/t202"}},
        }

    def _fake_list_project_work_packages_page(self, project_ref, *, skip=0, limit=200):
        safe_skip = int(skip or 0)
        safe_limit = int(limit or 200)
        items = preview_items[safe_skip : safe_skip + safe_limit]
        return {
            "project_ref": str(project_ref),
            "items": items,
            "total": len(preview_items),
            "skip": safe_skip,
            "limit": safe_limit,
        }

    def _fake_iter_project_work_packages(self, project_ref, *, page_size=200, max_items=5000):
        del project_ref, page_size
        for row in preview_items[: int(max_items)]:
            yield row

    monkeypatch.setattr(OpenProjectAdapter, "get_project", _fake_get_project)
    monkeypatch.setattr(OpenProjectAdapter, "list_project_work_packages_page", _fake_list_project_work_packages_page)
    monkeypatch.setattr(OpenProjectAdapter, "iter_project_work_packages", _fake_iter_project_work_packages)

    try:
        updated = dict(before_integrations)
        op_cfg = dict(updated.get("openproject") or {})
        op_cfg["enabled"] = True
        op_cfg["base_url"] = "https://open-project.example.com"
        op_cfg["api_token"] = "settings-token"
        updated["openproject"] = op_cfg
        _write_integrations(updated)

        preview_res = client.get(
            "/api/v1/storage/openproject/projects/t202/work-packages/preview?skip=0&limit=2",
            headers=headers,
        )
        assert preview_res.status_code == 200, preview_res.text
        preview_body = preview_res.json()
        assert preview_body.get("ok") is True
        assert int(preview_body.get("total") or 0) == 2
        assert len(preview_body.get("items") or []) == 2
        assert str(preview_body.get("project", {}).get("identifier") or "") == "t202"

        import_res = client.post(
            "/api/v1/storage/openproject/projects/t202/import",
            headers=headers,
            json={"max_items": 10, "page_size": 5},
        )
        assert import_res.status_code == 200, import_res.text
        import_body = import_res.json()
        run = import_body.get("run") or {}
        run_id = int(run.get("id") or 0)
        assert run_id > 0
        assert str(run.get("run_no") or "").startswith("OPP-")
        assert run.get("status_code") == "COMPLETED"
        assert int(run.get("created_rows") or 0) == 2
        summary = import_body.get("summary") or {}
        assert str(summary.get("run_type") or "") == "project_snapshot"
        assert int(summary.get("created_rows") or 0) == 2

        rows_res = client.get(
            f"/api/v1/storage/openproject/import/runs/{run_id}/rows?skip=0&limit=10",
            headers=headers,
        )
        assert rows_res.status_code == 200, rows_res.text
        rows = rows_res.json().get("rows") or []
        assert len(rows) == 2
        assert all(str(row.get("execution_status") or "") == "IMPORTED" for row in rows)
    finally:
        _write_integrations(before_integrations)
        if run_id > 0:
            _delete_import_run(run_id)


def test_openproject_project_preview_returns_404_on_missing_project(monkeypatch) -> None:
    headers = _admin_headers()
    before_integrations = _read_integrations()

    def _fake_get_project(self, project_ref):
        raise RuntimeError(f"OpenProject project fetch failed for `{project_ref}`: HTTP 404")

    monkeypatch.setattr(OpenProjectAdapter, "get_project", _fake_get_project)

    try:
        updated = dict(before_integrations)
        op_cfg = dict(updated.get("openproject") or {})
        op_cfg["enabled"] = True
        op_cfg["base_url"] = "https://open-project.example.com"
        op_cfg["api_token"] = "settings-token"
        updated["openproject"] = op_cfg
        _write_integrations(updated)

        response = client.get(
            "/api/v1/storage/openproject/projects/missing/work-packages/preview?skip=0&limit=10",
            headers=headers,
        )
        assert response.status_code == 404, response.text
    finally:
        _write_integrations(before_integrations)
