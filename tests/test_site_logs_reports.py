from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

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
        "equipment_rows": [{"equipment_code": "CRN", "equipment_label": "Crane", "claimed_status": "ACTIVE", "claimed_hours": 6.0, "sort_order": 0}],
        "activity_rows": [{"activity_code": "A-1", "activity_title": "Execution", "claimed_progress_pct": claimed_progress, "sort_order": 0}],
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
    )
    consultant = create_scoped_user_and_login(
        client,
        admin,
        org_type="consultant",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="rp_consultant",
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
            "equipment_rows": [{"sort_order": 0, "verified_status": "IDLE", "verified_hours": 4.0}],
            "activity_rows": [{"sort_order": 0, "verified_progress_pct": 22.5}],
            "note": "verified",
        },
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert verify_daily.status_code == 200, verify_daily.text

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
