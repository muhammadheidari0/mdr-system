from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.db.models import SiteLog
from app.db.session import SessionLocal
from app.main import app
from tests.site_logs_helpers import (
    admin_headers,
    create_scoped_user_and_login,
    ensure_project_discipline,
)


client = TestClient(app)


def _create_log(
    headers: dict[str, str],
    *,
    project_code: str,
    discipline_code: str,
    organization_id: int,
    log_type: str,
    claimed_count: int,
    claimed_hours: float,
    claimed_progress: float,
) -> int:
    payload = {
        "log_type": log_type,
        "project_code": project_code,
        "discipline_code": discipline_code,
        "organization_id": int(organization_id),
        "log_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
        "weather": "CLEAR",
        "summary": f"{log_type} report",
        "manpower_rows": [{"role_code": "WORKER", "role_label": "Worker", "claimed_count": claimed_count, "claimed_hours": claimed_hours, "sort_order": 0}],
        "equipment_rows": [
            {
                "equipment_code": "CRN",
                "equipment_label": "Crane",
                "work_location": "North bay",
                "claimed_count": 3,
                "claimed_status": "ACTIVE",
                "claimed_hours": 6.0,
                "sort_order": 0,
            }
        ],
        "activity_rows": [{"activity_code": "A-1", "activity_title": "Execution", "claimed_progress_pct": claimed_progress, "sort_order": 0}],
        "material_rows": [
            {
                "material_code": "CEM",
                "title": "Cement",
                "consumption_location": "Batching plant",
                "unit": "bag",
                "incoming_quantity": 4,
                "consumed_quantity": 2,
                "cumulative_quantity": 12,
                "sort_order": 0,
            }
        ],
    }
    res = client.post("/api/v1/site-logs/create", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    return int(res.json().get("data", {}).get("id") or 0)


def test_site_logs_reports_volume_variance_progress() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    contractor = create_scoped_user_and_login(
        client,
        admin,
        org_type="contractor",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="rp_contractor",
        organization_role="manager",
    )
    consultant = create_scoped_user_and_login(
        client,
        admin,
        org_type="consultant",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="rp_consultant",
        organization_role="manager",
    )
    contractor_headers = contractor["headers"]  # type: ignore[assignment]
    consultant_headers = consultant["headers"]  # type: ignore[assignment]

    daily_id = _create_log(
        contractor_headers,  # type: ignore[arg-type]
        project_code=project_code,
        discipline_code=discipline_code,
        organization_id=int(contractor.get("organization_id") or 0),
        log_type="DAILY",
        claimed_count=10,
        claimed_hours=80.0,
        claimed_progress=25.0,
    )
    assert daily_id > 0
    submit_daily = client.post(f"/api/v1/site-logs/{daily_id}/submit", json={"note": "submit daily"}, headers=contractor_headers)  # type: ignore[arg-type]
    assert submit_daily.status_code == 200, submit_daily.text
    verify_daily = client.post(
        f"/api/v1/site-logs/{daily_id}/verify",
        json={
            "manpower_rows": [{"sort_order": 0, "verified_count": 8, "verified_hours": 76.0}],
            "equipment_rows": [{"sort_order": 0, "verified_count": 2, "verified_status": "IDLE", "verified_hours": 4.0}],
            "activity_rows": [{"sort_order": 0, "verified_progress_pct": 22.5}],
            "note": "verified",
        },
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert verify_daily.status_code == 200, verify_daily.text
    db = SessionLocal()
    try:
        daily_row = db.query(SiteLog).filter(SiteLog.id == daily_id).first()
        assert daily_row is not None
        daily_row.work_status = "LEGACY_WORK_STATUS"
        db.commit()
    finally:
        db.close()

    weekly_id = _create_log(
        contractor_headers,  # type: ignore[arg-type]
        project_code=project_code,
        discipline_code=discipline_code,
        organization_id=int(contractor.get("organization_id") or 0),
        log_type="WEEKLY",
        claimed_count=14,
        claimed_hours=96.0,
        claimed_progress=31.0,
    )
    assert weekly_id > 0
    submit_weekly = client.post(f"/api/v1/site-logs/{weekly_id}/submit", json={"note": "submit weekly"}, headers=contractor_headers)  # type: ignore[arg-type]
    assert submit_weekly.status_code == 200, submit_weekly.text

    volume_res = client.get(
        f"/api/v1/site-logs/reports/volume?project_code={project_code}&discipline_code={discipline_code}",
        headers=admin,
    )
    assert volume_res.status_code == 200, volume_res.text
    volume_body = volume_res.json()
    assert volume_body.get("ok") is True
    by_type = volume_body.get("summary", {}).get("by_type", {})
    assert int(by_type.get("DAILY", 0)) >= 1
    assert int(by_type.get("WEEKLY", 0)) >= 1

    variance_res = client.get(
        f"/api/v1/site-logs/reports/variance?project_code={project_code}&discipline_code={discipline_code}",
        headers=admin,
    )
    assert variance_res.status_code == 200, variance_res.text
    variance_body = variance_res.json()
    assert variance_body.get("ok") is True
    assert int(variance_body.get("count", 0)) >= 1
    variance_rows = variance_body.get("data", [])
    assert any(str(row.get("log_no", "")).strip() for row in variance_rows)
    assert any(abs(float(row.get("manpower_count_delta", 0))) > 0 for row in variance_rows)
    assert any(abs(float(row.get("equipment_count_delta", 0))) > 0 for row in variance_rows)

    progress_res = client.get(
        f"/api/v1/site-logs/reports/progress?project_code={project_code}&discipline_code={discipline_code}",
        headers=admin,
    )
    assert progress_res.status_code == 200, progress_res.text
    progress_body = progress_res.json()
    assert progress_body.get("ok") is True
    assert int(progress_body.get("count", 0)) >= 1
    summary = progress_body.get("summary", {})
    assert "claimed_avg_progress_pct" in summary
    assert "verified_avg_progress_pct" in summary

    table_res = client.get(
        f"/api/v1/site-logs/reports/table?project_code={project_code}&discipline_code={discipline_code}&sort_by=log_no&sort_dir=asc&page_size=5000",
        headers=admin,
    )
    assert table_res.status_code == 200, table_res.text
    table_body = table_res.json()
    assert table_body.get("ok") is True
    assert table_body.get("columns")
    assert int(table_body.get("pagination", {}).get("total", 0)) >= 2
    table_rows = table_body.get("data", [])
    assert any(int(row.get("log_id") or 0) == daily_id for row in table_rows)
    daily_row = next(row for row in table_rows if int(row.get("log_id") or 0) == daily_id)
    assert daily_row.get("log_no")
    assert daily_row.get("status_code") == "VERIFIED"
    assert float(daily_row.get("claimed_manpower_count") or 0) == 10
    assert float(daily_row.get("verified_manpower_count") or 0) == 8
    assert float(daily_row.get("manpower_count_delta") or 0) == -2
    assert float(daily_row.get("verified_avg_progress_pct") or 0) == 22.5
    table_summary = table_body.get("summary", {})
    assert int(table_summary.get("total", 0)) >= 2
    assert int(table_summary.get("verified", 0)) >= 1

    manpower_res = client.get(
        f"/api/v1/site-logs/reports/table?project_code={project_code}&discipline_code={discipline_code}&report_section=manpower&page_size=5000",
        headers=admin,
    )
    assert manpower_res.status_code == 200, manpower_res.text
    manpower_body = manpower_res.json()
    assert manpower_body.get("report_section") == "manpower"
    assert any(column.get("key") == "role_label" for column in manpower_body.get("columns", []))
    manpower_rows = manpower_body.get("data", [])
    assert any(int(row.get("log_id") or 0) == daily_id and row.get("role_label") == "Worker" for row in manpower_rows)
    assert float(manpower_body.get("summary", {}).get("claimed_count") or 0) >= 24

    equipment_res = client.get(
        f"/api/v1/site-logs/reports/table?project_code={project_code}&discipline_code={discipline_code}&report_section=equipment&page_size=5000",
        headers=admin,
    )
    assert equipment_res.status_code == 200, equipment_res.text
    equipment_body = equipment_res.json()
    assert equipment_body.get("report_section") == "equipment"
    assert any(column.get("key") == "equipment_label" for column in equipment_body.get("columns", []))
    assert any(column.get("key") == "work_location" for column in equipment_body.get("columns", []))
    assert any(row.get("equipment_label") == "Crane" and row.get("work_location") == "North bay" for row in equipment_body.get("data", []))

    material_res = client.get(
        f"/api/v1/site-logs/reports/table?project_code={project_code}&discipline_code={discipline_code}&report_section=material&page_size=5000",
        headers=admin,
    )
    assert material_res.status_code == 200, material_res.text
    material_body = material_res.json()
    assert material_body.get("report_section") == "material"
    assert any(column.get("key") == "material_title" for column in material_body.get("columns", []))
    assert any(column.get("key") == "consumption_location" for column in material_body.get("columns", []))
    assert any(row.get("material_title") == "Cement" and row.get("consumption_location") == "Batching plant" for row in material_body.get("data", []))
    assert float(material_body.get("summary", {}).get("incoming_quantity") or 0) >= 8

    activity_res = client.get(
        f"/api/v1/site-logs/reports/table?project_code={project_code}&discipline_code={discipline_code}&report_section=activity&page_size=5000",
        headers=admin,
    )
    assert activity_res.status_code == 200, activity_res.text
    activity_body = activity_res.json()
    assert activity_body.get("report_section") == "activity"
    assert any(column.get("key") == "activity_title" for column in activity_body.get("columns", []))
    assert any(row.get("activity_title") == "Execution" for row in activity_body.get("data", []))

    verified_filter_res = client.get(
        f"/api/v1/site-logs/reports/table?project_code={project_code}&status_code=VERIFIED&organization_id={contractor.get('organization_id')}",
        headers=admin,
    )
    assert verified_filter_res.status_code == 200, verified_filter_res.text
    verified_rows = verified_filter_res.json().get("data", [])
    assert any(int(row.get("log_id") or 0) == daily_id for row in verified_rows)
    assert all(row.get("status_code") == "VERIFIED" for row in verified_rows)

    csv_res = client.get(
        f"/api/v1/site-logs/reports/table.csv?project_code={project_code}&discipline_code={discipline_code}",
        headers=admin,
    )
    assert csv_res.status_code == 200, csv_res.text
    assert "text/csv" in csv_res.headers.get("content-type", "")
    csv_text = csv_res.content.decode("utf-8-sig")
    header_line = csv_text.splitlines()[0]
    assert "log_no" in header_line
    assert "claimed_manpower_count" in header_line
    assert "verified_avg_progress_pct" in header_line
    assert "log_id" in header_line
