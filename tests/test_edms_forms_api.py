from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import CommItem, Discipline, PermitQcPermit, Project, SiteLog, WorkInstruction
from app.db.session import SessionLocal
from app.main import app
from tests.site_logs_helpers import (
    admin_headers,
    create_scoped_user_and_login,
    ensure_org,
)


client = TestClient(app)


def _project_code(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:5].upper()}"


def _ensure_project_and_discipline(project_code: str, discipline_code: str) -> None:
    with SessionLocal() as db:
        if not db.query(Project.id).filter(Project.code == project_code).first():
            db.add(Project(code=project_code, name_e=f"Project {project_code}", is_active=True))
        if not db.query(Discipline.code).filter(Discipline.code == discipline_code).first():
            db.add(Discipline(code=discipline_code, name_e=f"Discipline {discipline_code}"))
        db.commit()


def _seed_forms(
    *,
    project_code: str,
    discipline_code: str,
    contractor_org_id: int,
    consultant_org_id: int,
    extra_project_code: str,
) -> dict[str, int]:
    now = datetime.utcnow()
    with SessionLocal() as db:
        site_log = SiteLog(
            log_no=f"{project_code}-SLOG-{uuid4().hex[:6].upper()}",
            log_type="DAILY",
            project_code=project_code,
            discipline_code=discipline_code,
            organization_id=contractor_org_id,
            log_date=now,
            current_work_summary="EDMS forms site log",
            status_code="SUBMITTED",
        )
        db.add(site_log)

        rfi = CommItem(
            item_no=f"{project_code}-RFI-{uuid4().hex[:6].upper()}",
            item_type="RFI",
            project_code=project_code,
            discipline_code=discipline_code,
            organization_id=contractor_org_id,
            recipient_org_id=consultant_org_id,
            title="EDMS forms RFI",
            status_code="OPEN",
            priority="NORMAL",
            response_due_date=now - timedelta(days=2),
        )
        ncr = CommItem(
            item_no=f"{project_code}-NCR-{uuid4().hex[:6].upper()}",
            item_type="NCR",
            project_code=project_code,
            discipline_code=discipline_code,
            organization_id=consultant_org_id,
            recipient_org_id=contractor_org_id,
            title="EDMS forms NCR",
            status_code="ISSUED",
            priority="NORMAL",
            response_due_date=now + timedelta(days=3),
        )
        instruction = WorkInstruction(
            instruction_no=f"{project_code}-TECH-{discipline_code}-{uuid4().hex[:4].upper()}",
            legacy_subtype="INSTRUCTION",
            is_legacy_readonly=False,
            project_code=project_code,
            discipline_code=discipline_code,
            organization_id=contractor_org_id,
            recipient_org_id=consultant_org_id,
            title="EDMS forms Work Instruction",
            description="EDMS forms work instruction detail",
            status_code="OPEN",
            priority="NORMAL",
            response_due_date=now + timedelta(days=4),
        )
        db.add_all([rfi, ncr, instruction])

        permit = PermitQcPermit(
            permit_no=f"{project_code}-PQC-{uuid4().hex[:6].upper()}",
            permit_date=now,
            title="EDMS forms Permit QC",
            status_code="SUBMITTED",
            project_code=project_code,
            discipline_code=discipline_code,
            organization_id=contractor_org_id,
            contractor_org_id=contractor_org_id,
            consultant_org_id=consultant_org_id,
        )
        db.add(permit)

        other_log = SiteLog(
            log_no=f"{extra_project_code}-SLOG-{uuid4().hex[:6].upper()}",
            log_type="DAILY",
            project_code=extra_project_code,
            discipline_code=discipline_code,
            organization_id=contractor_org_id,
            log_date=now,
            current_work_summary="Out of scope site log",
            status_code="SUBMITTED",
        )
        db.add(other_log)
        db.commit()
        db.refresh(site_log)
        db.refresh(rfi)
        db.refresh(instruction)
        db.refresh(permit)
        return {
            "site_log_id": int(site_log.id),
            "rfi_id": int(rfi.id),
            "instruction_id": int(instruction.id),
            "permit_id": int(permit.id),
        }


def test_edms_forms_requires_independent_permission() -> None:
    admin = admin_headers(client)
    project_code = _project_code("EF")
    discipline_code = f"D{uuid4().hex[:3].upper()}"
    _ensure_project_and_discipline(project_code, discipline_code)
    user = create_scoped_user_and_login(
        client,
        admin,
        org_type="dcc",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix=f"edms_forms_no_perm_{uuid4().hex[:4]}",
        role="user",
        organization_role="user",
    )

    response = client.get("/api/v1/edms/forms/list", headers=user["headers"])  # type: ignore[arg-type]
    assert response.status_code == 403, response.text


def test_edms_forms_navigation_and_list_respect_scope() -> None:
    admin = admin_headers(client)
    project_code = _project_code("EF")
    other_project_code = _project_code("EX")
    discipline_code = f"D{uuid4().hex[:3].upper()}"
    _ensure_project_and_discipline(project_code, discipline_code)
    _ensure_project_and_discipline(other_project_code, discipline_code)
    contractor_org_id = ensure_org(client, admin, org_type="contractor", code_prefix="EF_CON")
    consultant_org_id = ensure_org(client, admin, org_type="consultant", code_prefix="EF_CNS")
    seeded = _seed_forms(
        project_code=project_code,
        discipline_code=discipline_code,
        contractor_org_id=contractor_org_id,
        consultant_org_id=consultant_org_id,
        extra_project_code=other_project_code,
    )

    user = create_scoped_user_and_login(
        client,
        admin,
        org_type="dcc",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix=f"edms_forms_scope_{uuid4().hex[:4]}",
        role="project_control",
        organization_role="project_control",
    )
    headers = user["headers"]  # type: ignore[assignment]

    nav = client.get("/api/v1/auth/navigation", headers=headers)
    assert nav.status_code == 200, nav.text
    nav_body = nav.json()
    assert nav_body.get("edms_tabs", {}).get("forms") is True
    assert list((nav_body.get("edms_tabs") or {}).keys())[-1] == "forms"

    response = client.get("/api/v1/edms/forms/list?limit=20", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True
    rows = body.get("data") or []
    assert {row.get("form_type") for row in rows} >= {"SITE_LOG", "RFI", "NCR", "WORK_INSTRUCTION", "PERMIT_QC"}
    assert all(row.get("project_code") == project_code for row in rows)
    assert seeded["site_log_id"] in {
        int(row.get("source_id") or 0) for row in rows if row.get("source_type") == "site_log"
    }
    assert body.get("summary", {}).get("overdue", 0) >= 1
    rfi_rows = [row for row in rows if row.get("form_type") == "RFI"]
    assert rfi_rows and rfi_rows[0].get("is_overdue") is True
    assert all(row.get("can_open_source") is False for row in rows)

    filtered = client.get("/api/v1/edms/forms/list?form_type=RFI&overdue_only=true", headers=headers)
    assert filtered.status_code == 200, filtered.text
    filtered_rows = filtered.json().get("data") or []
    assert filtered_rows
    assert all(row.get("form_type") == "RFI" and row.get("is_overdue") is True for row in filtered_rows)


def test_edms_forms_source_open_flag_requires_source_module_permission() -> None:
    admin = admin_headers(client)
    project_code = _project_code("EF")
    discipline_code = f"D{uuid4().hex[:3].upper()}"
    _ensure_project_and_discipline(project_code, discipline_code)
    contractor_org_id = ensure_org(client, admin, org_type="contractor", code_prefix="EF_CON")
    consultant_org_id = ensure_org(client, admin, org_type="consultant", code_prefix="EF_CNS")
    _seed_forms(
        project_code=project_code,
        discipline_code=discipline_code,
        contractor_org_id=contractor_org_id,
        consultant_org_id=consultant_org_id,
        extra_project_code=project_code,
    )
    user = create_scoped_user_and_login(
        client,
        admin,
        org_type="dcc",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix=f"edms_forms_source_{uuid4().hex[:4]}",
        role="project_control",
        organization_role="project_control",
    )
    headers = user["headers"]  # type: ignore[assignment]

    matrix_res = client.get("/api/v1/settings/permissions/matrix?category=dcc", headers=admin)
    assert matrix_res.status_code == 200, matrix_res.text
    original = deepcopy(matrix_res.json().get("matrix") or {})
    modified = deepcopy(original)
    modified.setdefault("project_control", {})
    for permission in (
        "hub_consultant:read",
        "module_comm_items_consultant:read",
        "comm_items:read",
    ):
        modified["project_control"][permission] = True
    save = client.post(
        "/api/v1/settings/permissions/matrix?category=dcc",
        json={"matrix": modified},
        headers=admin,
    )
    assert save.status_code == 200, save.text

    try:
        response = client.get("/api/v1/edms/forms/list?form_type=RFI", headers=headers)
        assert response.status_code == 200, response.text
        rows = response.json().get("data") or []
        assert rows
        assert rows[0].get("can_open_source") is True
        assert rows[0].get("target_hub") == "consultant"
        assert rows[0].get("target_tab") == "control"
    finally:
        restore = client.post(
            "/api/v1/settings/permissions/matrix?category=dcc",
            json={"matrix": original},
            headers=admin,
        )
        assert restore.status_code == 200, restore.text
