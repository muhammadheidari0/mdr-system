from __future__ import annotations

from io import BytesIO
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.db.models import OpenProjectImportRun
from app.db.session import SessionLocal
from app.main import app
from app.services.openproject_adapter import OpenProjectAdapter
from app.services.storage_policy import get_storage_integrations, set_storage_integrations
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _build_upload_bytes_with_invalid_row() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Task_Table1"
    ws.append(["Name", "Duration", "Start_Date", "Finish_Date", "Predecessors", "Resource_Names"])
    ws.append(["Task A", "5 days", "14 February 2026 08:00 AM", "19 February 2026 05:00 PM", "", "Crew A"])
    ws.append(["", "3 days", "bad-date", "", "", ""])
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def _delete_import_run(run_id: int) -> None:
    with SessionLocal() as db:
        db.query(OpenProjectImportRun).filter(OpenProjectImportRun.id == int(run_id)).delete()
        db.commit()


def _read_integrations() -> dict:
    with SessionLocal() as db:
        return get_storage_integrations(db)


def _write_integrations(payload: dict) -> None:
    with SessionLocal() as db:
        set_storage_integrations(db, payload)
        db.commit()


def test_openproject_import_execute_success_and_idempotency(monkeypatch) -> None:
    headers = _admin_headers()
    before_integrations = _read_integrations()
    run_id = 0
    create_calls: list[dict[str, Any]] = []

    def _fake_get_work_package(self, work_package_id: int) -> dict[str, Any]:
        return {
            "id": int(work_package_id),
            "_links": {
                "project": {"href": "/api/v3/projects/5"},
                "type": {"href": "/api/v3/types/1"},
            },
        }

    def _fake_create_work_package(self, payload: dict[str, Any]) -> dict[str, Any]:
        create_calls.append(dict(payload))
        created_id = 8000 + len(create_calls)
        return {
            "id": created_id,
            "_links": {"self": {"href": f"/api/v3/work_packages/{created_id}"}},
        }

    monkeypatch.setattr(OpenProjectAdapter, "get_work_package", _fake_get_work_package)
    monkeypatch.setattr(OpenProjectAdapter, "create_work_package", _fake_create_work_package)

    try:
        validate_res = client.post(
            "/api/v1/storage/openproject/import/validate",
            headers=headers,
            files={
                "file": (
                    "openproject_import.xlsx",
                    _build_upload_bytes_with_invalid_row(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert validate_res.status_code == 200, validate_res.text
        run_id = int(validate_res.json().get("run", {}).get("id") or 0)
        assert run_id > 0

        updated_integrations = dict(before_integrations)
        op_cfg = dict(updated_integrations.get("openproject") or {})
        op_cfg["enabled"] = True
        op_cfg["base_url"] = "https://open-project.example.com"
        op_cfg["api_token"] = "settings-token"
        op_cfg["default_work_package_id"] = "321"
        updated_integrations["openproject"] = op_cfg
        _write_integrations(updated_integrations)

        execute_res = client.post(
            f"/api/v1/storage/openproject/import/runs/{run_id}/execute",
            headers=headers,
            json={},
        )
        assert execute_res.status_code == 200, execute_res.text
        run = execute_res.json().get("run") or {}
        assert run.get("status_code") == "COMPLETED"
        assert int(run.get("created_rows") or 0) == 1
        assert int(run.get("failed_rows") or 0) == 0
        assert len(create_calls) == 1

        rows_res = client.get(
            f"/api/v1/storage/openproject/import/runs/{run_id}/rows?skip=0&limit=20",
            headers=headers,
        )
        assert rows_res.status_code == 200, rows_res.text
        rows = rows_res.json().get("rows") or []
        statuses = {int(row.get("row_no") or 0): str(row.get("execution_status") or "") for row in rows}
        assert "CREATED" in statuses.values()
        assert "SKIPPED" in statuses.values()

        activity_res = client.get("/api/v1/storage/openproject/activity?limit=20", headers=headers)
        assert activity_res.status_code == 200, activity_res.text
        items = activity_res.json().get("items") or []
        assert any(str(item.get("source") or "") == "import" for item in items)

        second_execute = client.post(
            f"/api/v1/storage/openproject/import/runs/{run_id}/execute",
            headers=headers,
            json={},
        )
        assert second_execute.status_code == 409, second_execute.text
    finally:
        _write_integrations(before_integrations)
        if run_id > 0:
            _delete_import_run(run_id)
