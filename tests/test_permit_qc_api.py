from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.db.models import Discipline, Organization, Project
from app.db.session import SessionLocal
from app.main import app
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _seed_project_discipline_and_org() -> tuple[str, str, int]:
    project_code = f"PQ{uuid.uuid4().hex[:6]}".upper()
    discipline_code = f"PD{uuid.uuid4().hex[:4]}".upper()
    consultant_code = f"CONS_{uuid.uuid4().hex[:8]}".upper()

    with SessionLocal() as db:
        project = db.query(Project).filter(Project.code == project_code).first()
        if not project:
            db.add(
                Project(
                    code=project_code,
                    name_e=f"Permit QC {project_code}",
                    name_p=f"Permit QC {project_code}",
                    is_active=True,
                )
            )

        discipline = db.query(Discipline).filter(Discipline.code == discipline_code).first()
        if not discipline:
            db.add(
                Discipline(
                    code=discipline_code,
                    name_e=f"Permit QC {discipline_code}",
                    name_p=f"Permit QC {discipline_code}",
                )
            )

        consultant_org = db.query(Organization).filter(Organization.code == consultant_code).first()
        if not consultant_org:
            consultant_org = Organization(
                code=consultant_code,
                name=f"Permit Consultant {consultant_code}",
                org_type="consultant",
                is_active=True,
            )
            db.add(consultant_org)
        db.commit()
        db.refresh(consultant_org)
        return project_code, discipline_code, int(consultant_org.id)


def _seed_template(
    headers: dict[str, str],
    *,
    project_code: str,
    discipline_code: str,
    consultant_org_id: int,
) -> tuple[int, int, int]:
    template_code = f"TPL_{uuid.uuid4().hex[:7]}".upper()
    create_template = client.post(
        "/api/v1/permit-qc/templates/upsert",
        headers=headers,
        json={
            "code": template_code,
            "name": f"Template {template_code}",
            "description": "Core permit QC template",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "is_active": True,
            "is_default": True,
        },
    )
    assert create_template.status_code == 200, create_template.text
    template = (create_template.json().get("data") or {})
    template_id = int(template.get("id") or 0)
    assert template_id > 0

    add_station = client.post(
        f"/api/v1/permit-qc/templates/{template_id}/stations/upsert",
        headers=headers,
        json={
            "station_key": "S1",
            "station_label": "Consultant Station",
            "organization_id": consultant_org_id,
            "is_required": True,
            "is_active": True,
            "sort_order": 1,
        },
    )
    assert add_station.status_code == 200, add_station.text
    station_rows = (add_station.json().get("data") or {}).get("stations") or []
    station_id = int(station_rows[0].get("id") or 0)
    assert station_id > 0

    add_check = client.post(
        f"/api/v1/permit-qc/templates/{template_id}/checks/upsert",
        headers=headers,
        json={
            "station_id": station_id,
            "check_code": "CHK_BOOL",
            "check_label": "Boolean check",
            "check_type": "BOOLEAN",
            "is_required": True,
            "is_active": True,
            "sort_order": 1,
        },
    )
    assert add_check.status_code == 200, add_check.text
    check_rows = (((add_check.json().get("data") or {}).get("stations") or [{}])[0].get("checks") or [])
    check_id = int(check_rows[0].get("id") or 0)
    assert check_id > 0
    return template_id, station_id, check_id


def test_permit_qc_core_flow_with_review_timeline_and_attachments() -> None:
    headers = _admin_headers()
    project_code, discipline_code, consultant_org_id = _seed_project_discipline_and_org()
    template_id, _, _ = _seed_template(
        headers,
        project_code=project_code,
        discipline_code=discipline_code,
        consultant_org_id=consultant_org_id,
    )

    permit_no = f"{project_code}-PERMIT-{uuid.uuid4().hex[:6]}".upper()
    create_res = client.post(
        "/api/v1/permit-qc/create",
        headers=headers,
        json={
            "module_key": "contractor",
            "permit_no": permit_no,
            "permit_date": "2026-02-28T00:00:00",
            "title": "Deck quality permit",
            "description": "initial draft",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "template_id": template_id,
            "consultant_org_id": consultant_org_id,
        },
    )
    assert create_res.status_code == 200, create_res.text
    created = (create_res.json().get("data") or {})
    permit_id = int(created.get("id") or 0)
    assert permit_id > 0
    assert created.get("status_code") == "DRAFT"

    update_res = client.put(
        f"/api/v1/permit-qc/{permit_id}",
        headers=headers,
        json={"title": "Deck quality permit v2", "description": "updated in draft"},
    )
    assert update_res.status_code == 200, update_res.text
    assert (update_res.json().get("data") or {}).get("title") == "Deck quality permit v2"

    submit_res = client.post(f"/api/v1/permit-qc/{permit_id}/submit", headers=headers)
    assert submit_res.status_code == 200, submit_res.text
    submitted = (submit_res.json().get("data") or {})
    assert submitted.get("status_code") == "SUBMITTED"
    stations = submitted.get("stations") or []
    assert len(stations) == 1
    station_id = int(stations[0].get("id") or 0)
    station_checks = stations[0].get("checks") or []
    assert len(station_checks) == 1
    check_id = int(station_checks[0].get("id") or 0)

    return_res = client.post(
        f"/api/v1/permit-qc/{permit_id}/review",
        headers=headers,
        json={
            "station_id": station_id,
            "action": "RETURN",
            "note": "Need correction",
            "checks": [{"check_id": check_id, "value_bool": False, "note": "failed"}],
        },
    )
    assert return_res.status_code == 200, return_res.text
    assert (return_res.json().get("data") or {}).get("status_code") == "RETURNED"

    update_after_return = client.put(
        f"/api/v1/permit-qc/{permit_id}",
        headers=headers,
        json={"description": "corrected after return"},
    )
    assert update_after_return.status_code == 200, update_after_return.text

    resubmit_res = client.post(f"/api/v1/permit-qc/{permit_id}/resubmit", headers=headers)
    assert resubmit_res.status_code == 200, resubmit_res.text
    assert (resubmit_res.json().get("data") or {}).get("status_code") == "SUBMITTED"

    approve_res = client.post(
        f"/api/v1/permit-qc/{permit_id}/review",
        headers=headers,
        json={
            "station_id": station_id,
            "action": "APPROVE",
            "checks": [{"check_id": check_id, "value_bool": True, "note": "ok"}],
        },
    )
    assert approve_res.status_code == 200, approve_res.text
    assert (approve_res.json().get("data") or {}).get("status_code") == "APPROVED"

    upload_res = client.post(
        f"/api/v1/permit-qc/{permit_id}/attachments",
        headers=headers,
        data={"module_key": "contractor", "file_kind": "attachment"},
        files={"file": ("permit_qc_sample.pdf", b"%PDF-1.4 permit qc test", "application/pdf")},
    )
    assert upload_res.status_code == 200, upload_res.text
    attachment_id = int((upload_res.json().get("data") or {}).get("id") or 0)
    assert attachment_id > 0

    attachments_res = client.get(
        f"/api/v1/permit-qc/{permit_id}/attachments?module_key=contractor",
        headers=headers,
    )
    assert attachments_res.status_code == 200, attachments_res.text
    attachments = attachments_res.json().get("data") or []
    assert any(int(item.get("id") or 0) == attachment_id for item in attachments)

    timeline_res = client.get(
        f"/api/v1/permit-qc/{permit_id}/timeline?module_key=contractor",
        headers=headers,
    )
    assert timeline_res.status_code == 200, timeline_res.text
    event_types = {str(item.get("event_type") or "") for item in (timeline_res.json().get("data") or [])}
    assert "CREATE" in event_types
    assert "SUBMIT" in event_types
    assert "RESUBMIT" in event_types
    assert "REVIEW_RETURN" in event_types
    assert "REVIEW_APPROVE" in event_types
    assert "ATTACHMENT_UPLOAD" in event_types

    delete_attachment_res = client.delete(
        f"/api/v1/permit-qc/{permit_id}/attachments?module_key=contractor&attachment_id={attachment_id}",
        headers=headers,
    )
    assert delete_attachment_res.status_code == 200, delete_attachment_res.text
    assert delete_attachment_res.json().get("ok") is True


def test_permit_qc_cancel_in_draft() -> None:
    headers = _admin_headers()
    project_code, discipline_code, consultant_org_id = _seed_project_discipline_and_org()
    permit_no = f"{project_code}-CAN-{uuid.uuid4().hex[:6]}".upper()

    create_res = client.post(
        "/api/v1/permit-qc/create",
        headers=headers,
        json={
            "module_key": "contractor",
            "permit_no": permit_no,
            "permit_date": "2026-02-28T00:00:00",
            "title": "Cancel case",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "consultant_org_id": consultant_org_id,
        },
    )
    assert create_res.status_code == 200, create_res.text
    permit_id = int((create_res.json().get("data") or {}).get("id") or 0)
    assert permit_id > 0

    cancel_res = client.post(
        f"/api/v1/permit-qc/{permit_id}/cancel?note=cancelled%20by%20test",
        headers=headers,
    )
    assert cancel_res.status_code == 200, cancel_res.text
    cancelled = cancel_res.json().get("data") or {}
    assert cancelled.get("status_code") == "CANCELLED"
