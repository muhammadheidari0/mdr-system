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


def _create_draft(
    headers: dict[str, str],
    *,
    project_code: str,
    discipline_code: str,
    organization_id: int,
    include_rows: bool = True,
) -> int:
    payload = {
        "log_type": "DAILY",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "organization_id": int(organization_id),
        "log_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
        "weather": "CLEAR",
        "summary": "Daily site log from api test",
        "manpower_rows": (
            [{"role_code": "FOREMAN", "role_label": "Foreman", "claimed_count": 4, "claimed_hours": 8.0, "sort_order": 0}]
            if include_rows
            else []
        ),
        "equipment_rows": [],
        "activity_rows": [],
    }
    res = client.post("/api/v1/site-logs/create", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    data = body.get("data", {})
    assert str(data.get("status_code")) == "DRAFT"
    assert str(data.get("log_no", "")).startswith(f"{project_code}-SLOG-")
    return int(data.get("id") or 0)


def test_site_logs_api_core_workflow_and_guards() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    contractor = create_scoped_user_and_login(
        client,
        admin,
        org_type="contractor",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="site_contractor",
    )
    consultant = create_scoped_user_and_login(
        client,
        admin,
        org_type="consultant",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="site_consultant",
    )

    contractor_headers = contractor["headers"]  # type: ignore[assignment]
    consultant_headers = consultant["headers"]  # type: ignore[assignment]

    draft_id = _create_draft(
        contractor_headers,  # type: ignore[arg-type]
        project_code=project_code,
        discipline_code=discipline_code,
        organization_id=int(contractor.get("organization_id") or 0),
        include_rows=True,
    )
    assert draft_id > 0

    empty_draft_id = _create_draft(
        contractor_headers,  # type: ignore[arg-type]
        project_code=project_code,
        discipline_code=discipline_code,
        organization_id=int(contractor.get("organization_id") or 0),
        include_rows=False,
    )
    submit_empty = client.post(f"/api/v1/site-logs/{empty_draft_id}/submit", json={"note": "submit"}, headers=contractor_headers)  # type: ignore[arg-type]
    assert submit_empty.status_code == 400, submit_empty.text

    contractor_verified_write = client.put(
        f"/api/v1/site-logs/{draft_id}",
        json={
            "manpower_rows": [
                {
                    "role_code": "FOREMAN",
                    "role_label": "Foreman",
                    "claimed_count": 4,
                    "claimed_hours": 8.0,
                    "verified_count": 9,
                    "sort_order": 0,
                }
            ]
        },
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert contractor_verified_write.status_code == 403, contractor_verified_write.text

    submit_ok = client.post(f"/api/v1/site-logs/{draft_id}/submit", json={"note": "submit"}, headers=contractor_headers)  # type: ignore[arg-type]
    assert submit_ok.status_code == 200, submit_ok.text
    assert str(submit_ok.json().get("data", {}).get("status_code")) == "SUBMITTED"

    consultant_create = client.post(
        "/api/v1/site-logs/create",
        json={
            "log_type": "DAILY",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "organization_id": int(consultant.get("organization_id") or 0),
            "log_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
            "summary": "Consultant should not create",
        },
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert consultant_create.status_code == 403, consultant_create.text

    verify_without_values = client.post(
        f"/api/v1/site-logs/{draft_id}/verify",
        json={"note": "verify without values"},
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert verify_without_values.status_code == 400, verify_without_values.text

    verify_ok = client.post(
        f"/api/v1/site-logs/{draft_id}/verify",
        json={"manpower_rows": [{"sort_order": 0, "verified_count": 5, "verified_hours": 8.0}], "note": "verified"},
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert verify_ok.status_code == 200, verify_ok.text
    assert str(verify_ok.json().get("data", {}).get("status_code")) == "VERIFIED"

    contractor_update_after_verify = client.put(
        f"/api/v1/site-logs/{draft_id}",
        json={"summary": "should fail after verify"},
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert contractor_update_after_verify.status_code == 409, contractor_update_after_verify.text
