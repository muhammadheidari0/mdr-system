from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.db.models import OpenProjectImportRun
from app.db.session import SessionLocal
from app.main import app
from app.services.storage_policy import get_storage_integrations, set_storage_integrations
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _build_upload_bytes(*, include_task_sheet: bool = True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Task_Table1" if include_task_sheet else "Sheet1"
    ws.append(["Name", "Duration", "Start_Date", "Finish_Date", "Predecessors", "Resource_Names"])
    ws.append(["Task A", "5 days", "14 February 2026 08:00 AM", "19 February 2026 05:00 PM", "", "Crew A"])
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


def _restore_integrations(payload: dict) -> None:
    with SessionLocal() as db:
        set_storage_integrations(db, payload)
        db.commit()


def test_openproject_import_validate_success_and_runs_list() -> None:
    headers = _admin_headers()
    run_id = 0
    try:
        response = client.post(
            "/api/v1/storage/openproject/import/validate",
            headers=headers,
            files={
                "file": (
                    "openproject_import.xlsx",
                    _build_upload_bytes(include_task_sheet=True),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("ok") is True
        run = body.get("run") or {}
        summary = body.get("summary") or {}
        run_id = int(run.get("id") or 0)
        assert run_id > 0
        assert run.get("status_code") == "VALIDATED"
        assert int(run.get("valid_rows") or 0) == 1
        assert "pass1_created_rows" in summary
        assert "pass1_failed_rows" in summary
        assert "pass2_relation_created" in summary
        assert "pass2_relation_failed" in summary

        runs_res = client.get("/api/v1/storage/openproject/import/runs?limit=10", headers=headers)
        assert runs_res.status_code == 200, runs_res.text
        runs = runs_res.json().get("runs", [])
        assert any(int(item.get("id") or 0) == run_id for item in runs)
    finally:
        if run_id > 0:
            _delete_import_run(run_id)


def test_openproject_import_validate_missing_task_sheet_returns_400() -> None:
    headers = _admin_headers()
    response = client.post(
        "/api/v1/storage/openproject/import/validate",
        headers=headers,
        files={
            "file": (
                "openproject_import.xlsx",
                _build_upload_bytes(include_task_sheet=False),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 400, response.text
    assert "Task_Table1" in str(response.json().get("detail") or "")


def test_openproject_import_execute_without_default_wp_returns_400() -> None:
    headers = _admin_headers()
    before_integrations = _read_integrations()
    run_id = 0
    try:
        validate_res = client.post(
            "/api/v1/storage/openproject/import/validate",
            headers=headers,
            files={
                "file": (
                    "openproject_import.xlsx",
                    _build_upload_bytes(include_task_sheet=True),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert validate_res.status_code == 200, validate_res.text
        run_id = int(validate_res.json().get("run", {}).get("id") or 0)
        assert run_id > 0

        next_integrations = dict(before_integrations)
        next_openproject = dict(next_integrations.get("openproject") or {})
        next_openproject["enabled"] = True
        next_openproject["default_work_package_id"] = ""
        next_openproject["base_url"] = "https://open-project.example.com"
        next_openproject["api_token"] = "token-from-settings"
        next_integrations["openproject"] = next_openproject
        _restore_integrations(next_integrations)

        execute_res = client.post(
            f"/api/v1/storage/openproject/import/runs/{run_id}/execute",
            headers=headers,
            json={},
        )
        assert execute_res.status_code == 400, execute_res.text
        assert "default_work_package_id" in str(execute_res.json().get("detail") or "")
    finally:
        _restore_integrations(before_integrations)
        if run_id > 0:
            _delete_import_run(run_id)
