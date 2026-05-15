from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import Discipline, DocumentRevision, MdrDocument, Project
from app.db.session import SessionLocal
from app.main import app
from tests.site_logs_helpers import admin_headers, create_scoped_user_and_login


client = TestClient(app)


def _code(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:6].upper()}"


def _ensure_project_and_discipline(project_code: str, discipline_code: str) -> None:
    with SessionLocal() as db:
        if not db.query(Project.id).filter(Project.code == project_code).first():
            db.add(Project(code=project_code, name_e=f"Project {project_code}", is_active=True))
        if not db.query(Discipline.code).filter(Discipline.code == discipline_code).first():
            db.add(Discipline(code=discipline_code, name_e=f"Discipline {discipline_code}"))
        db.commit()


def _seed_meeting_relation_document(project_code: str, discipline_code: str) -> tuple[int, str]:
    doc_no = f"{project_code}-MOMREL-{uuid4().hex[:5].upper()}"
    with SessionLocal() as db:
        document = MdrDocument(
            doc_number=doc_no,
            doc_title_e="Meeting relation document",
            doc_title_p="Meeting relation document",
            subject="Meeting relation document",
            project_code=project_code,
            phase_code=None,
            discipline_code=discipline_code,
            package_code="00",
            block=None,
            level_code=None,
            mdr_code=None,
        )
        db.add(document)
        db.flush()
        db.add(DocumentRevision(document_id=int(document.id), revision="00", status="IFA"))
        db.commit()
        return int(document.id), doc_no


def test_meeting_minutes_crud_resolutions_attachments_and_filters() -> None:
    admin = admin_headers(client)
    project_code = _code("MM")
    discipline_code = _code("D")[:8]
    _ensure_project_and_discipline(project_code, discipline_code)

    catalog = client.get("/api/v1/meeting-minutes/catalog", headers=admin)
    assert catalog.status_code == 200, catalog.text
    assert catalog.json().get("ok") is True

    meeting_no = f"{project_code}-MOM-{uuid4().hex[:6].upper()}"
    create_res = client.post(
        "/api/v1/meeting-minutes/create",
        json={
            "meeting_no": meeting_no,
            "title": "Coordination meeting",
            "project_code": project_code,
            "meeting_type": "Coordination",
            "meeting_date": datetime.utcnow().isoformat(),
            "location": "Site office",
            "participants": "Consultant, Contractor",
            "status": "Open",
        },
        headers=admin,
    )
    assert create_res.status_code == 200, create_res.text
    minute = create_res.json().get("data") or {}
    minute_id = int(minute.get("id") or 0)
    assert minute_id > 0

    list_res = client.get(
        f"/api/v1/meeting-minutes/list?search={meeting_no}&project_code={project_code}",
        headers=admin,
    )
    assert list_res.status_code == 200, list_res.text
    assert list_res.json().get("total") == 1

    due_yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
    resolution_res = client.post(
        f"/api/v1/meeting-minutes/{minute_id}/resolutions",
        json={
            "resolution_no": "R-001",
            "description": "Submit revised shop drawings",
            "responsible_name": "Contractor PM",
            "due_date": due_yesterday,
            "status": "Open",
            "priority": "High",
        },
        headers=admin,
    )
    assert resolution_res.status_code == 200, resolution_res.text
    resolution = resolution_res.json().get("data") or {}
    resolution_id = int(resolution.get("id") or 0)
    assert resolution_id > 0
    assert resolution.get("is_overdue") is True

    overdue_list = client.get(
        "/api/v1/meeting-minutes/list?open_resolutions_only=true&overdue_only=true",
        headers=admin,
    )
    assert overdue_list.status_code == 200, overdue_list.text
    rows = overdue_list.json().get("data") or []
    assert any(int(row.get("id") or 0) == minute_id for row in rows)
    assert int((overdue_list.json().get("summary") or {}).get("overdue_resolutions") or 0) >= 1

    upload = client.post(
        f"/api/v1/meeting-minutes/{minute_id}/attachments/upload",
        data={"file_kind": "main"},
        files={"file": ("minutes.pdf", BytesIO(b"%PDF-1.4\nmeeting minutes\n%%EOF"), "application/pdf")},
        headers=admin,
    )
    assert upload.status_code == 200, upload.text
    attachment = upload.json().get("data") or {}
    attachment_id = int(attachment.get("id") or 0)
    assert attachment_id > 0
    assert attachment.get("file_kind") == "main"

    download = client.get(f"/api/v1/meeting-minutes/attachments/{attachment_id}/download", headers=admin)
    assert download.status_code == 200, download.text
    assert b"meeting minutes" in download.content

    delete_attachment = client.delete(f"/api/v1/meeting-minutes/attachments/{attachment_id}", headers=admin)
    assert delete_attachment.status_code == 200, delete_attachment.text
    attachments_after_delete = client.get(f"/api/v1/meeting-minutes/{minute_id}/attachments", headers=admin)
    assert attachments_after_delete.status_code == 200, attachments_after_delete.text
    assert attachments_after_delete.json().get("data") == []

    update_resolution = client.put(
        f"/api/v1/meeting-minutes/resolutions/{resolution_id}",
        json={"status": "Done"},
        headers=admin,
    )
    assert update_resolution.status_code == 200, update_resolution.text
    assert update_resolution.json().get("data", {}).get("status") == "Done"

    delete_resolution = client.delete(f"/api/v1/meeting-minutes/resolutions/{resolution_id}", headers=admin)
    assert delete_resolution.status_code == 200, delete_resolution.text
    resolutions_after_delete = client.get(f"/api/v1/meeting-minutes/{minute_id}/resolutions", headers=admin)
    assert resolutions_after_delete.status_code == 200, resolutions_after_delete.text
    assert resolutions_after_delete.json().get("data") == []

    update_minute = client.put(
        f"/api/v1/meeting-minutes/{minute_id}",
        json={"status": "Closed", "notes": "Closed after follow-up"},
        headers=admin,
    )
    assert update_minute.status_code == 200, update_minute.text
    assert update_minute.json().get("data", {}).get("status") == "Closed"

    delete_minute = client.delete(f"/api/v1/meeting-minutes/{minute_id}", headers=admin)
    assert delete_minute.status_code == 200, delete_minute.text
    list_after_delete = client.get(f"/api/v1/meeting-minutes/list?search={meeting_no}", headers=admin)
    assert list_after_delete.status_code == 200, list_after_delete.text
    assert list_after_delete.json().get("total") == 0


def test_meeting_minutes_navigation_and_read_only_permission() -> None:
    admin = admin_headers(client)
    project_code = _code("MMRO")
    discipline_code = _code("DR")[:8]
    _ensure_project_and_discipline(project_code, discipline_code)

    user = create_scoped_user_and_login(
        client,
        admin,
        org_type="dcc",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix=f"meeting_minutes_ro_{uuid4().hex[:4]}",
        role="viewer",
        organization_role="viewer",
    )
    headers = user["headers"]  # type: ignore[assignment]

    nav = client.get("/api/v1/auth/navigation", headers=headers)
    assert nav.status_code == 200, nav.text
    assert nav.json().get("edms_tabs", {}).get("meeting_minutes") is True

    read_res = client.get("/api/v1/meeting-minutes/list", headers=headers)
    assert read_res.status_code == 200, read_res.text

    blocked_create = client.post(
        "/api/v1/meeting-minutes/create",
        json={
            "meeting_no": f"{project_code}-BLOCKED",
            "title": "Blocked",
            "project_code": project_code,
        },
        headers=headers,  # type: ignore[arg-type]
    )
    assert blocked_create.status_code == 403, blocked_create.text


def test_meeting_minutes_auto_number_print_and_external_relations() -> None:
    admin = admin_headers(client)
    project_code = _code("MMA")
    discipline_code = _code("DA")[:8]
    _ensure_project_and_discipline(project_code, discipline_code)
    meeting_date = "2026-05-11"

    preview = client.get(
        f"/api/v1/meeting-minutes/next-number?project_code={project_code}&meeting_date={meeting_date}",
        headers=admin,
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body.get("meeting_no") == f"{project_code}-MOM-2605-0001"
    assert preview_body.get("next_serial") == 1

    first = client.post(
        "/api/v1/meeting-minutes/create",
        json={
            "title": "Auto numbered meeting",
            "project_code": project_code,
            "meeting_type": "Coordination",
            "meeting_date": f"{meeting_date}T00:00:00",
            "status": "Open",
        },
        headers=admin,
    )
    assert first.status_code == 200, first.text
    first_data = first.json().get("data") or {}
    minute_id = int(first_data.get("id") or 0)
    meeting_no = str(first_data.get("meeting_no") or "")
    assert minute_id > 0
    assert meeting_no == f"{project_code}-MOM-2605-0001"

    second = client.post(
        "/api/v1/meeting-minutes/create",
        json={
            "title": "Second auto numbered meeting",
            "project_code": project_code,
            "meeting_date": f"{meeting_date}T00:00:00",
        },
        headers=admin,
    )
    assert second.status_code == 200, second.text
    assert (second.json().get("data") or {}).get("meeting_no") == f"{project_code}-MOM-2605-0002"

    resolution = client.post(
        f"/api/v1/meeting-minutes/{minute_id}/resolutions",
        json={
            "description": "Close coordination action",
            "responsible_name": "Contractor",
            "due_date": "2026-05-20T00:00:00",
            "status": "Open",
            "priority": "High",
            "sort_order": 10,
        },
        headers=admin,
    )
    assert resolution.status_code == 200, resolution.text
    assert (resolution.json().get("data") or {}).get("resolution_no") == "R-001"

    upload = client.post(
        f"/api/v1/meeting-minutes/{minute_id}/attachments/upload",
        data={"file_kind": "attachment"},
        files={"file": ("mom-attachment.pdf", BytesIO(b"%PDF-1.4\nmeeting print attachment\n"), "application/pdf")},
        headers=admin,
    )
    assert upload.status_code == 200, upload.text

    _, doc_no = _seed_meeting_relation_document(project_code, discipline_code)
    doc_relation = client.post(
        f"/api/v1/meeting-minutes/{minute_id}/relations",
        json={"target_entity_type": "document", "target_code": doc_no, "relation_type": "references"},
        headers=admin,
    )
    assert doc_relation.status_code == 200, doc_relation.text
    assert (doc_relation.json().get("data") or {}).get("target_entity_type") == "document"

    reference_no = f"{project_code}-CO-O-{uuid4().hex[:6].upper()}"
    corr_create = client.post(
        "/api/v1/correspondence/create",
        json={
            "project_code": project_code,
            "issuing_code": project_code,
            "category_code": "CO",
            "discipline_code": discipline_code,
            "doc_type": "Correspondence",
            "direction": "O",
            "reference_no": reference_no,
            "subject": "Meeting relation correspondence",
            "sender": "DCC",
            "recipient": "Engineering",
            "status": "Open",
            "priority": "Normal",
        },
        headers=admin,
    )
    assert corr_create.status_code == 200, corr_create.text

    corr_relation = client.post(
        f"/api/v1/meeting-minutes/{minute_id}/relations",
        json={"target_entity_type": "correspondence", "target_code": reference_no, "relation_type": "related"},
        headers=admin,
    )
    assert corr_relation.status_code == 200, corr_relation.text
    corr_relation_id = str((corr_relation.json().get("data") or {}).get("id") or "")
    assert corr_relation_id.startswith("external:")

    relations = client.get(f"/api/v1/meeting-minutes/{minute_id}/relations", headers=admin)
    assert relations.status_code == 200, relations.text
    outgoing = relations.json().get("outgoing") or []
    assert {(row.get("target_entity_type"), row.get("target_code")) for row in outgoing} >= {
        ("document", doc_no),
        ("correspondence", reference_no),
    }

    filtered = client.get(
        f"/api/v1/meeting-minutes/list?has_attachments=true&relation_search={reference_no}",
        headers=admin,
    )
    assert filtered.status_code == 200, filtered.text
    assert any(int(row.get("id") or 0) == minute_id for row in filtered.json().get("data") or [])

    print_preview = client.get(f"/api/v1/meeting-minutes/{minute_id}/print-preview", headers=admin)
    assert print_preview.status_code == 200, print_preview.text
    assert "text/html" in print_preview.headers.get("content-type", "")
    assert meeting_no in print_preview.text
    assert "R-001" in print_preview.text

    delete_relation = client.delete(
        f"/api/v1/meeting-minutes/{minute_id}/relations/{corr_relation_id}",
        headers=admin,
    )
    assert delete_relation.status_code == 200, delete_relation.text
