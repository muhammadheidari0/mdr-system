from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.site_logs_helpers import (
    admin_headers,
    create_scoped_user_and_login,
    ensure_project_discipline,
)


client = TestClient(app)


def _seed_activity_with_pms(
    headers: dict[str, str],
    *,
    project_code: str,
    organization_id: int,
) -> tuple[str, int, str]:
    activity_code = f"PCM{uuid4().hex[:5].upper()}"
    activity_res = client.post(
        "/api/v1/settings/site-log-activity-catalog/upsert",
        json={
            "project_code": project_code,
            "organization_id": organization_id,
            "activity_code": activity_code,
            "activity_title": "Project control measured activity",
            "default_location": "Deck A",
            "default_unit": "m3",
            "sort_order": 10,
            "is_active": True,
        },
        headers=headers,
    )
    assert activity_res.status_code == 200, activity_res.text
    activity_id = int((activity_res.json().get("item") or {}).get("id") or 0)
    assert activity_id > 0

    template_code = f"PCPMS{uuid4().hex[:4].upper()}"
    template_res = client.post(
        "/api/v1/settings/site-log-pms/templates/upsert",
        json={
            "code": template_code,
            "title": "Project Control PMS",
            "sort_order": 10,
            "is_active": True,
            "steps": [
                {"step_code": "WORK", "step_title": "Work Done", "weight_pct": 70, "sort_order": 10, "is_active": True},
                {"step_code": "QC", "step_title": "QC Passed", "weight_pct": 30, "sort_order": 20, "is_active": True},
            ],
        },
        headers=headers,
    )
    assert template_res.status_code == 200, template_res.text
    template_id = int((template_res.json().get("item") or {}).get("id") or 0)
    assert template_id > 0

    mapping_res = client.post(
        "/api/v1/settings/site-log-pms/mappings/apply",
        json={"activity_ids": [activity_id], "template_id": template_id, "overwrite": False},
        headers=headers,
    )
    assert mapping_res.status_code == 200, mapping_res.text
    mapping_id = int(((mapping_res.json().get("items") or [{}])[0]).get("pms_mapping_id") or 0)
    assert mapping_id > 0
    return activity_code, mapping_id, template_code


def _create_submitted_site_log(
    headers: dict[str, str],
    *,
    project_code: str,
    discipline_code: str,
    organization_id: int,
    activity_code: str,
    mapping_id: int,
) -> int:
    payload = {
        "log_type": "DAILY",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "organization_id": organization_id,
        "log_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
        "weather": "CLEAR",
        "current_work_summary": "Contractor submitted activity measurement source.",
        "activity_rows": [
            {
                "activity_code": activity_code,
                "activity_title": "Project control measured activity",
                "source_system": "CATALOG",
                "pms_mapping_id": mapping_id,
                "pms_step_code": "WORK",
                "location": "Deck A",
                "unit": "m3",
                "today_quantity": 12.5,
                "cumulative_quantity": 44.0,
                "claimed_progress_pct": 42.0,
                "sort_order": 0,
            }
        ],
    }
    create_res = client.post("/api/v1/site-logs/create", json=payload, headers=headers)
    assert create_res.status_code == 200, create_res.text
    log_id = int((create_res.json().get("data") or {}).get("id") or 0)
    assert log_id > 0

    submit_res = client.post(f"/api/v1/site-logs/{log_id}/submit", json={"note": "submitted"}, headers=headers)
    assert submit_res.status_code == 200, submit_res.text
    assert (submit_res.json().get("data") or {}).get("status_code") == "SUBMITTED"
    return log_id


def test_project_control_activity_measurement_flow_and_exports() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)
    contractor = create_scoped_user_and_login(
        client,
        admin,
        org_type="contractor",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="pc_contractor",
        organization_role="manager",
    )
    contractor_headers = contractor["headers"]  # type: ignore[assignment]
    organization_id = int(contractor.get("organization_id") or 0)

    activity_code, mapping_id, template_code = _seed_activity_with_pms(
        admin,
        project_code=project_code,
        organization_id=organization_id,
    )
    log_id = _create_submitted_site_log(
        contractor_headers,  # type: ignore[arg-type]
        project_code=project_code,
        discipline_code=discipline_code,
        organization_id=organization_id,
        activity_code=activity_code,
        mapping_id=mapping_id,
    )

    list_res = client.get(
        f"/api/v1/project-control/activity-measurements?project_code={project_code}&activity_code={activity_code}",
        headers=admin,
    )
    assert list_res.status_code == 200, list_res.text
    body = list_res.json()
    assert body.get("ok") is True
    rows = body.get("data") or []
    assert len(rows) == 1
    row = rows[0]
    row_id = int(row.get("row_id") or 0)
    assert row_id > 0
    assert int(row.get("log_id") or 0) == log_id
    assert row.get("measurement_status") == "DRAFT"
    assert row.get("qc_status") == "PENDING"
    assert row.get("pms_template_code") == template_code
    assert [step.get("step_code") for step in row.get("pms_steps", [])] == ["WORK", "QC"]

    patch_res = client.patch(
        f"/api/v1/project-control/activity-measurements/{row_id}",
        json={
            "supervisor_today_quantity": 11.0,
            "supervisor_cumulative_quantity": 43.0,
            "supervisor_unit": "m3",
            "verified_progress_pct": 40.0,
        },
        headers=admin,
    )
    assert patch_res.status_code == 200, patch_res.text
    patched = patch_res.json().get("data") or {}
    assert patched.get("measurement_status") == "MEASURED"
    assert float(patched.get("supervisor_today_quantity") or 0) == 11.0

    blocked_transition = client.post(
        f"/api/v1/project-control/activity-measurements/{row_id}/transition",
        json={"target": "VERIFIED"},
        headers=admin,
    )
    assert blocked_transition.status_code == 400, blocked_transition.text

    qc_res = client.patch(
        f"/api/v1/project-control/activity-measurements/{row_id}",
        json={"qc_status": "PASSED", "qc_note": "Accepted after field check."},
        headers=admin,
    )
    assert qc_res.status_code == 200, qc_res.text
    assert (qc_res.json().get("data") or {}).get("qc_status") == "PASSED"

    verified_res = client.post(
        f"/api/v1/project-control/activity-measurements/{row_id}/transition",
        json={"target": "VERIFIED"},
        headers=admin,
    )
    assert verified_res.status_code == 200, verified_res.text
    assert (verified_res.json().get("data") or {}).get("measurement_status") == "VERIFIED"

    source_res = client.get(f"/api/v1/project-control/activity-measurements/{row_id}/source-report", headers=admin)
    assert source_res.status_code == 200, source_res.text
    assert int((source_res.json().get("data") or {}).get("site_log", {}).get("id") or 0) == log_id

    wide_res = client.get(
        f"/api/v1/project-control/activity-measurements.csv?project_code={project_code}&activity_code={activity_code}&shape=wide",
        headers=admin,
    )
    assert wide_res.status_code == 200, wide_res.text
    wide_text = wide_res.content.decode("utf-8-sig")
    assert "row_id,log_id,log_no" in wide_text.splitlines()[0]
    assert activity_code in wide_text

    long_res = client.get(
        f"/api/v1/project-control/activity-measurements.csv?project_code={project_code}&activity_code={activity_code}&shape=long",
        headers=admin,
    )
    assert long_res.status_code == 200, long_res.text
    long_text = long_res.content.decode("utf-8-sig")
    assert "step_code" in long_text.splitlines()[0]
    assert long_text.count(activity_code) >= 2
    assert "WORK" in long_text and "QC" in long_text

    viewer = create_scoped_user_and_login(
        client,
        admin,
        org_type="consultant",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="pc_viewer",
        organization_role="viewer",
    )
    denied = client.patch(
        f"/api/v1/project-control/activity-measurements/{row_id}",
        json={"supervisor_today_quantity": 10.0},
        headers=viewer["headers"],  # type: ignore[arg-type]
    )
    assert denied.status_code == 403, denied.text
