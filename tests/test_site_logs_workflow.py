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


def _new_log_payload(project_code: str, discipline_code: str, organization_id: int) -> dict:
    return {
        "log_type": "DAILY",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "organization_id": int(organization_id),
        "log_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
        "weather": "CLEAR",
        "summary": "workflow test log",
        "manpower_rows": [{"role_code": "WORKER", "role_label": "Worker", "claimed_count": 3, "claimed_hours": 8, "sort_order": 0}],
        "equipment_rows": [],
        "activity_rows": [],
    }


def test_site_logs_workflow_status_constraints_and_read_only_after_verify() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    contractor = create_scoped_user_and_login(
        client,
        admin,
        org_type="contractor",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="wf_contractor",
        organization_role="manager",
    )
    consultant = create_scoped_user_and_login(
        client,
        admin,
        org_type="consultant",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="wf_consultant",
        organization_role="manager",
    )

    contractor_headers = contractor["headers"]  # type: ignore[assignment]
    consultant_headers = consultant["headers"]  # type: ignore[assignment]

    create_non_draft = client.post(
        "/api/v1/site-logs/create",
        json={**_new_log_payload(project_code, discipline_code, int(contractor.get("organization_id") or 0)), "status_code": "SUBMITTED"},
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert create_non_draft.status_code == 400, create_non_draft.text

    create_res = client.post(
        "/api/v1/site-logs/create",
        json=_new_log_payload(project_code, discipline_code, int(contractor.get("organization_id") or 0)),
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert create_res.status_code == 200, create_res.text
    log_id = int(create_res.json().get("data", {}).get("id") or 0)
    assert log_id > 0

    contractor_verify_attempt = client.post(
        f"/api/v1/site-logs/{log_id}/verify",
        json={"manpower_rows": [{"sort_order": 0, "verified_count": 3}]},
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert contractor_verify_attempt.status_code == 403, contractor_verify_attempt.text

    submit_res = client.post(f"/api/v1/site-logs/{log_id}/submit", json={"note": "submitted"}, headers=contractor_headers)  # type: ignore[arg-type]
    assert submit_res.status_code == 200, submit_res.text

    submit_again = client.post(f"/api/v1/site-logs/{log_id}/submit", json={"note": "again"}, headers=contractor_headers)  # type: ignore[arg-type]
    assert submit_again.status_code == 409, submit_again.text

    return_res = client.post(
        f"/api/v1/site-logs/{log_id}/return",
        json={"note": "revise manpower hours"},
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert return_res.status_code == 200, return_res.text
    assert str(return_res.json().get("data", {}).get("status_code")) == "RETURNED"

    comments_res = client.get(f"/api/v1/site-logs/{log_id}/comments", headers=consultant_headers)  # type: ignore[arg-type]
    assert comments_res.status_code == 200, comments_res.text
    assert any(str(item.get("comment_text") or "") == "revise manpower hours" for item in comments_res.json().get("data", []))

    update_returned = client.put(
        f"/api/v1/site-logs/{log_id}",
        json={**_new_log_payload(project_code, discipline_code, int(contractor.get("organization_id") or 0)), "summary": "updated after return"},
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert update_returned.status_code == 200, update_returned.text

    resubmit = client.post(f"/api/v1/site-logs/{log_id}/submit", json={"note": "resubmitted"}, headers=contractor_headers)  # type: ignore[arg-type]
    assert resubmit.status_code == 200, resubmit.text
    assert str(resubmit.json().get("data", {}).get("status_code")) == "SUBMITTED"

    verify_res = client.post(
        f"/api/v1/site-logs/{log_id}/verify",
        json={"manpower_rows": [{"sort_order": 0, "verified_count": 2, "verified_hours": 7.5}], "note": "checked"},
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert verify_res.status_code == 200, verify_res.text
    assert str(verify_res.json().get("data", {}).get("status_code")) == "VERIFIED"

    consultant_comment_after_verify = client.post(
        f"/api/v1/site-logs/{log_id}/comments",
        json={"comment_text": "should fail"},
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert consultant_comment_after_verify.status_code == 409, consultant_comment_after_verify.text

    contractor_attachment_after_verify = client.post(
        f"/api/v1/site-logs/{log_id}/attachments",
        data={"file_kind": "attachment", "section_code": "GENERAL"},
        files={"file": ("deny.txt", b"deny", "text/plain")},
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert contractor_attachment_after_verify.status_code == 409, contractor_attachment_after_verify.text
