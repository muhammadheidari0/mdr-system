from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.security import get_password_hash
from app.db.models import Discipline, Organization, Project, User
from app.db.session import SessionLocal
from app.main import app
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _token_headers(email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, response.text
    token = str((response.json() or {}).get("access_token") or "").strip()
    assert token
    return {"Authorization": f"Bearer {token}"}


def _seed_org_and_user(*, org_type: str, role: str) -> tuple[int, str, str]:
    key = uuid.uuid4().hex[:8]
    org_code = f"{org_type[:3].upper()}_{key}".upper()
    email = f"permit_{org_type}_{key}@mdr.local"
    password = f"Pass!{key}123"
    with SessionLocal() as db:
        org = db.query(Organization).filter(Organization.code == org_code).first()
        if not org:
            org = Organization(
                code=org_code,
                name=f"{org_type.title()} Org {key}",
                org_type=org_type,
                is_active=True,
            )
            db.add(org)
            db.flush()

        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                full_name=f"{org_type.title()} User {key}",
                role=role,
                organization_id=int(org.id),
                organization_role="viewer",
                is_active=True,
            )
            db.add(user)
        else:
            user.hashed_password = get_password_hash(password)
            user.role = role
            user.organization_id = int(org.id)
            user.organization_role = "viewer"
            user.is_active = True
        db.commit()
        return int(org.id), email, password


def _seed_project_discipline() -> tuple[str, str]:
    project_code = f"PP{uuid.uuid4().hex[:6]}".upper()
    discipline_code = f"PX{uuid.uuid4().hex[:4]}".upper()
    with SessionLocal() as db:
        if not db.query(Project).filter(Project.code == project_code).first():
            db.add(Project(code=project_code, name_e=project_code, name_p=project_code, is_active=True))
        if not db.query(Discipline).filter(Discipline.code == discipline_code).first():
            db.add(Discipline(code=discipline_code, name_e=discipline_code, name_p=discipline_code))
        db.commit()
    return project_code, discipline_code


def _seed_template(
    headers: dict[str, str],
    *,
    project_code: str,
    discipline_code: str,
    consultant_org_id: int,
) -> int:
    template_code = f"TPR_{uuid.uuid4().hex[:6]}".upper()
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
            "station_key": "CONS_STAGE",
            "station_label": "Consultant Stage",
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
            "check_code": "CONS_BOOL",
            "check_label": "Consultant bool check",
            "check_type": "BOOLEAN",
            "is_required": True,
            "is_active": True,
            "sort_order": 1,
        },
    )
    assert check_res.status_code == 200, check_res.text
    return template_id


def test_permit_qc_permissions_between_contractor_and_consultant() -> None:
    admin_headers = _admin_headers()
    project_code, discipline_code = _seed_project_discipline()
    contractor_org_id, contractor_email, contractor_password = _seed_org_and_user(org_type="contractor", role="user")
    consultant_org_id, consultant_email, consultant_password = _seed_org_and_user(org_type="consultant", role="user")

    _seed_template(
        admin_headers,
        project_code=project_code,
        discipline_code=discipline_code,
        consultant_org_id=consultant_org_id,
    )

    contractor_headers = _token_headers(contractor_email, contractor_password)
    consultant_headers = _token_headers(consultant_email, consultant_password)

    create_res = client.post(
        "/api/v1/permit-qc/create",
        headers=contractor_headers,
        json={
            "module_key": "contractor",
            "permit_no": f"{project_code}-RBAC-{uuid.uuid4().hex[:6]}".upper(),
            "permit_date": "2026-02-28T00:00:00",
            "title": "RBAC Permit",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "consultant_org_id": consultant_org_id,
        },
    )
    assert create_res.status_code == 200, create_res.text
    created = create_res.json().get("data") or {}
    permit_id = int(created.get("id") or 0)
    assert permit_id > 0

    submit_res = client.post(f"/api/v1/permit-qc/{permit_id}/submit", headers=contractor_headers)
    assert submit_res.status_code == 200, submit_res.text
    station_id = int((((submit_res.json().get("data") or {}).get("stations") or [{}])[0].get("id") or 0))
    assert station_id > 0

    contractor_review = client.post(
        f"/api/v1/permit-qc/{permit_id}/review",
        headers=contractor_headers,
        json={"station_id": station_id, "action": "APPROVE", "checks": []},
    )
    assert contractor_review.status_code == 403, contractor_review.text

    consultant_review = client.post(
        f"/api/v1/permit-qc/{permit_id}/review",
        headers=consultant_headers,
        json={"station_id": station_id, "action": "APPROVE", "checks": []},
    )
    assert consultant_review.status_code == 200, consultant_review.text

    consultant_create = client.post(
        "/api/v1/permit-qc/create",
        headers=consultant_headers,
        json={
            "module_key": "contractor",
            "permit_no": f"{project_code}-CONS-{uuid.uuid4().hex[:6]}".upper(),
            "permit_date": "2026-02-28T00:00:00",
            "title": "Consultant should not create contractor permit",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "consultant_org_id": consultant_org_id,
        },
    )
    assert consultant_create.status_code == 403, consultant_create.text

    contractor_list_consultant = client.get(
        "/api/v1/permit-qc/list?module_key=consultant&skip=0&limit=20",
        headers=contractor_headers,
    )
    assert contractor_list_consultant.status_code == 403, contractor_list_consultant.text

    consultant_list_contractor = client.get(
        "/api/v1/permit-qc/list?module_key=contractor&skip=0&limit=20",
        headers=consultant_headers,
    )
    assert consultant_list_contractor.status_code == 403, consultant_list_contractor.text

    consultant_templates = client.get("/api/v1/permit-qc/templates", headers=consultant_headers)
    assert consultant_templates.status_code == 403, consultant_templates.text

    # Ensure contractor's org is the same as creator's org at create-time.
    detail_res = client.get(
        f"/api/v1/permit-qc/{permit_id}?module_key=contractor",
        headers=contractor_headers,
    )
    assert detail_res.status_code == 200, detail_res.text
    detail = detail_res.json().get("data") or {}
    assert int(detail.get("contractor_org_id") or 0) == contractor_org_id
