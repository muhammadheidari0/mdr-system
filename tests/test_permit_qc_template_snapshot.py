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


def _seed_project_discipline_org() -> tuple[str, str, int]:
    project_code = f"PS{uuid.uuid4().hex[:6]}".upper()
    discipline_code = f"PS{uuid.uuid4().hex[:4]}".upper()
    org_code = f"PCONS_{uuid.uuid4().hex[:7]}".upper()
    with SessionLocal() as db:
        if not db.query(Project).filter(Project.code == project_code).first():
            db.add(Project(code=project_code, name_e=project_code, name_p=project_code, is_active=True))
        if not db.query(Discipline).filter(Discipline.code == discipline_code).first():
            db.add(Discipline(code=discipline_code, name_e=discipline_code, name_p=discipline_code))
        org = db.query(Organization).filter(Organization.code == org_code).first()
        if not org:
            org = Organization(code=org_code, name=org_code, org_type="consultant", is_active=True)
            db.add(org)
            db.flush()
        db.commit()
        db.refresh(org)
        return project_code, discipline_code, int(org.id)


def _create_template_with_single_check(
    headers: dict[str, str],
    *,
    project_code: str,
    discipline_code: str,
    consultant_org_id: int,
    check_label: str,
) -> tuple[int, int, int]:
    template_code = f"SNAP_{uuid.uuid4().hex[:6]}".upper()
    template_res = client.post(
        "/api/v1/permit-qc/templates/upsert",
        headers=headers,
        json={
            "code": template_code,
            "name": f"Template {template_code}",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "is_active": True,
            "is_default": True,
        },
    )
    assert template_res.status_code == 200, template_res.text
    template_id = int((template_res.json().get("data") or {}).get("id") or 0)
    assert template_id > 0

    station_res = client.post(
        f"/api/v1/permit-qc/templates/{template_id}/stations/upsert",
        headers=headers,
        json={
            "station_key": "SNAP_STAGE",
            "station_label": "Snapshot Stage",
            "organization_id": consultant_org_id,
            "is_required": True,
            "is_active": True,
            "sort_order": 1,
        },
    )
    assert station_res.status_code == 200, station_res.text
    station_id = int((((station_res.json().get("data") or {}).get("stations") or [{}])[0].get("id") or 0))
    assert station_id > 0

    check_res = client.post(
        f"/api/v1/permit-qc/templates/{template_id}/checks/upsert",
        headers=headers,
        json={
            "station_id": station_id,
            "check_code": "SNAP_BOOL",
            "check_label": check_label,
            "check_type": "BOOLEAN",
            "is_required": True,
            "is_active": True,
            "sort_order": 1,
        },
    )
    assert check_res.status_code == 200, check_res.text
    check_rows = ((((check_res.json().get("data") or {}).get("stations") or [{}])[0].get("checks") or []))
    check_id = int((check_rows[0].get("id") or 0))
    assert check_id > 0
    return template_id, station_id, check_id


def _create_and_submit_permit(
    headers: dict[str, str],
    *,
    project_code: str,
    discipline_code: str,
    template_id: int,
    consultant_org_id: int,
    title: str,
) -> dict:
    permit_no = f"{project_code}-SNAP-{uuid.uuid4().hex[:6]}".upper()
    create_res = client.post(
        "/api/v1/permit-qc/create",
        headers=headers,
        json={
            "module_key": "contractor",
            "permit_no": permit_no,
            "permit_date": "2026-02-28T00:00:00",
            "title": title,
            "project_code": project_code,
            "discipline_code": discipline_code,
            "template_id": template_id,
            "consultant_org_id": consultant_org_id,
        },
    )
    assert create_res.status_code == 200, create_res.text
    permit_id = int((create_res.json().get("data") or {}).get("id") or 0)
    assert permit_id > 0

    submit_res = client.post(f"/api/v1/permit-qc/{permit_id}/submit", headers=headers)
    assert submit_res.status_code == 200, submit_res.text
    return submit_res.json().get("data") or {}


def test_permit_qc_template_snapshot_is_immutable_after_first_submit() -> None:
    headers = _admin_headers()
    project_code, discipline_code, consultant_org_id = _seed_project_discipline_org()
    template_id, station_id, check_id = _create_template_with_single_check(
        headers,
        project_code=project_code,
        discipline_code=discipline_code,
        consultant_org_id=consultant_org_id,
        check_label="Initial Snapshot Label",
    )

    first_permit = _create_and_submit_permit(
        headers,
        project_code=project_code,
        discipline_code=discipline_code,
        template_id=template_id,
        consultant_org_id=consultant_org_id,
        title="First permit before template update",
    )
    first_checks = (((first_permit.get("stations") or [{}])[0].get("checks") or []))
    assert first_checks
    assert first_checks[0].get("check_label") == "Initial Snapshot Label"

    update_check_res = client.post(
        f"/api/v1/permit-qc/templates/{template_id}/checks/upsert",
        headers=headers,
        json={
            "id": check_id,
            "station_id": station_id,
            "check_code": "SNAP_BOOL",
            "check_label": "Updated Template Label",
            "check_type": "BOOLEAN",
            "is_required": True,
            "is_active": True,
            "sort_order": 1,
        },
    )
    assert update_check_res.status_code == 200, update_check_res.text

    first_detail_res = client.get(
        f"/api/v1/permit-qc/{int(first_permit.get('id') or 0)}?module_key=contractor",
        headers=headers,
    )
    assert first_detail_res.status_code == 200, first_detail_res.text
    first_detail_checks = (((first_detail_res.json().get("data") or {}).get("stations") or [{}])[0].get("checks") or [])
    assert first_detail_checks[0].get("check_label") == "Initial Snapshot Label"

    second_permit = _create_and_submit_permit(
        headers,
        project_code=project_code,
        discipline_code=discipline_code,
        template_id=template_id,
        consultant_org_id=consultant_org_id,
        title="Second permit after template update",
    )
    second_checks = (((second_permit.get("stations") or [{}])[0].get("checks") or []))
    assert second_checks
    assert second_checks[0].get("check_label") == "Updated Template Label"
