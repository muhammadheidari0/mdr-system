from __future__ import annotations

import io
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import Discipline, DocumentRevision, MdrDocument, Project, Transmittal, TransmittalDoc
from app.db.session import SessionLocal
from app.main import app
from tests.auth_helpers import get_auth_headers


client = TestClient(app)

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _ensure_context(project_code: str, discipline_code: str = "GN") -> None:
    with SessionLocal() as db:
        if not db.query(Project.id).filter(Project.code == project_code).first():
            db.add(Project(code=project_code, name_e=f"Project {project_code}", is_active=True))
        if not db.query(Discipline.code).filter(Discipline.code == discipline_code).first():
            db.add(Discipline(code=discipline_code, name_e=f"Discipline {discipline_code}"))
        db.commit()


def _seed_document_and_transmittal(project_code: str, discipline_code: str = "GN") -> tuple[int, str, str]:
    doc_no = f"{project_code}-EGN{uuid4().hex[:4].upper()}01-TGEN"
    transmittal_no = f"{project_code}-T-O-C-{datetime.utcnow().strftime('%y%m')}{uuid4().hex[:3].upper()}"
    with SessionLocal() as db:
        document = MdrDocument(
            doc_number=doc_no,
            doc_title_e="Correspondence relation document",
            doc_title_p="Correspondence relation document",
            subject="Correspondence relation document",
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
        document_id = int(document.id or 0)
        db.add(DocumentRevision(document_id=int(document.id), revision="00", status="IFA"))
        transmittal = Transmittal(
            id=transmittal_no,
            project_code=project_code,
            direction="O",
            send_date=None,
            reply_due_date=None,
            sender="O",
            receiver="C",
            created_at=datetime.utcnow(),
            lifecycle_status="draft",
        )
        db.add(transmittal)
        db.add(
            TransmittalDoc(
                transmittal_id=transmittal_no,
                document_code=doc_no,
                document_title="Correspondence relation document",
                revision="00",
                status="IFA",
                electronic_copy=True,
                hard_copy=False,
            )
        )
        db.commit()
    return document_id, doc_no, transmittal_no


def test_correspondence_typeahead_preview_and_relations() -> None:
    headers = get_auth_headers(client)
    project_code = f"CR{uuid4().hex[:6].upper()}"
    discipline_code = "GN"
    _ensure_context(project_code, discipline_code)

    reference_no = f"{project_code}-CO-O-{uuid4().hex[:6].upper()}"
    create_res = client.post(
        "/api/v1/correspondence/create",
        json={
            "project_code": project_code,
            "issuing_code": project_code,
            "category_code": "CO",
            "discipline_code": discipline_code,
            "doc_type": "Correspondence",
            "direction": "O",
            "reference_no": reference_no,
            "subject": "Typeahead relation correspondence",
            "sender": "DCC",
            "recipient": "Engineering",
            "cc_recipients": "Design Team\nFinance Team",
            "status": "Open",
            "priority": "Normal",
        },
        headers=headers,
    )
    assert create_res.status_code == 200, create_res.text
    assert (create_res.json().get("data") or {}).get("cc_recipients") == "Design Team\nFinance Team"
    correspondence_id = int((create_res.json().get("data") or {}).get("id") or 0)
    assert correspondence_id > 0

    related_reference_no = f"{project_code}-CO-I-{uuid4().hex[:6].upper()}"
    related_create_res = client.post(
        "/api/v1/correspondence/create",
        json={
            "project_code": project_code,
            "issuing_code": project_code,
            "category_code": "CO",
            "discipline_code": discipline_code,
            "doc_type": "Correspondence",
            "direction": "I",
            "reference_no": related_reference_no,
            "subject": "Original correspondence for reply relation",
            "sender": "Engineering",
            "recipient": "DCC",
            "status": "Open",
            "priority": "Normal",
        },
        headers=headers,
    )
    assert related_create_res.status_code == 200, related_create_res.text
    related_correspondence_id = int((related_create_res.json().get("data") or {}).get("id") or 0)
    assert related_correspondence_id > 0

    attachment_res = client.post(
        f"/api/v1/correspondence/{correspondence_id}/attachments/upload",
        data={"file_kind": "attachment"},
        files={"file": ("attachment.pdf", io.BytesIO(b"%PDF-1.4\nattachment-preview\n"), "application/pdf")},
        headers=headers,
    )
    assert attachment_res.status_code == 200, attachment_res.text
    attachment_id = int((attachment_res.json().get("data") or {}).get("id") or 0)

    preview_without_letter = client.get(f"/api/v1/correspondence/{correspondence_id}/preview", headers=headers)
    assert preview_without_letter.status_code == 404, preview_without_letter.text
    assert b"attachment-preview" not in preview_without_letter.content

    original_res = client.post(
        f"/api/v1/correspondence/{correspondence_id}/attachments/upload",
        data={"file_kind": "original"},
        files={"file": ("editable.pdf", io.BytesIO(b"%PDF-1.4\neditable-preview\n"), "application/pdf")},
        headers=headers,
    )
    assert original_res.status_code == 200, original_res.text
    original_id = int((original_res.json().get("data") or {}).get("id") or 0)
    assert original_id > 0
    assert (original_res.json().get("data") or {}).get("preview_supported") is False

    preview_with_original_only = client.get(f"/api/v1/correspondence/{correspondence_id}/preview", headers=headers)
    assert preview_with_original_only.status_code == 404, preview_with_original_only.text
    assert b"editable-preview" not in preview_with_original_only.content

    image_attachment_res = client.post(
        f"/api/v1/correspondence/{correspondence_id}/attachments/upload",
        data={"file_kind": "attachment"},
        files={"file": ("attachment-image.png", io.BytesIO(PNG_1X1), "image/png")},
        headers=headers,
    )
    assert image_attachment_res.status_code == 200, image_attachment_res.text
    image_attachment_id = int((image_attachment_res.json().get("data") or {}).get("id") or 0)
    assert image_attachment_id > 0
    assert (image_attachment_res.json().get("data") or {}).get("preview_supported") is True

    letter_res = client.post(
        f"/api/v1/correspondence/{correspondence_id}/attachments/upload",
        data={"file_kind": "letter"},
        files={"file": ("letter.pdf", io.BytesIO(b"%PDF-1.4\nletter-preview\n"), "application/pdf")},
        headers=headers,
    )
    assert letter_res.status_code == 200, letter_res.text

    unsupported_res = client.post(
        f"/api/v1/correspondence/{correspondence_id}/attachments/upload",
        data={"file_kind": "attachment"},
        files={"file": ("notes.txt", io.BytesIO(b"plain text is download-only\n"), "text/plain")},
        headers=headers,
    )
    assert unsupported_res.status_code == 200, unsupported_res.text
    unsupported_id = int((unsupported_res.json().get("data") or {}).get("id") or 0)
    assert (unsupported_res.json().get("data") or {}).get("preview_supported") is False

    preview_res = client.get(f"/api/v1/correspondence/{correspondence_id}/preview", headers=headers)
    assert preview_res.status_code == 200, preview_res.text
    assert "inline" in preview_res.headers.get("content-disposition", "").lower()
    assert preview_res.headers.get("content-type", "").startswith("application/pdf")
    assert b"letter-preview" in preview_res.content
    assert b"attachment-preview" not in preview_res.content
    assert b"editable-preview" not in preview_res.content

    attachment_preview = client.get(f"/api/v1/correspondence/attachments/{attachment_id}/preview", headers=headers)
    assert attachment_preview.status_code == 200, attachment_preview.text
    assert "inline" in attachment_preview.headers.get("content-disposition", "").lower()
    assert b"attachment-preview" in attachment_preview.content

    original_preview = client.get(f"/api/v1/correspondence/attachments/{original_id}/preview", headers=headers)
    assert original_preview.status_code == 415, original_preview.text
    assert b"editable-preview" not in original_preview.content

    image_attachment_preview = client.get(
        f"/api/v1/correspondence/attachments/{image_attachment_id}/preview",
        headers=headers,
    )
    assert image_attachment_preview.status_code == 200, image_attachment_preview.text
    assert image_attachment_preview.headers.get("content-type", "").startswith("image/png")
    assert image_attachment_preview.content.startswith(b"\x89PNG")

    image_letter_res = client.post(
        f"/api/v1/correspondence/{correspondence_id}/attachments/upload",
        data={"file_kind": "letter"},
        files={"file": ("letter-image.png", io.BytesIO(PNG_1X1), "image/png")},
        headers=headers,
    )
    assert image_letter_res.status_code == 200, image_letter_res.text
    image_letter_preview = client.get(f"/api/v1/correspondence/{correspondence_id}/preview", headers=headers)
    assert image_letter_preview.status_code == 200, image_letter_preview.text
    assert image_letter_preview.headers.get("content-type", "").startswith("image/png")
    assert image_letter_preview.content.startswith(b"\x89PNG")

    unsupported_preview = client.get(
        f"/api/v1/correspondence/attachments/{unsupported_id}/preview",
        headers=headers,
    )
    assert unsupported_preview.status_code == 415, unsupported_preview.text
    assert "PDF" in unsupported_preview.json().get("detail", "")

    suggestions = client.get(f"/api/v1/correspondence/suggestions?q={reference_no[:10]}", headers=headers)
    assert suggestions.status_code == 200, suggestions.text
    assert any(item.get("reference_no") == reference_no for item in suggestions.json().get("items") or [])

    cc_search = client.get("/api/v1/correspondence/list?search=Finance%20Team", headers=headers)
    assert cc_search.status_code == 200, cc_search.text
    assert any(item.get("reference_no") == reference_no for item in cc_search.json().get("data") or [])

    update_cc = client.put(
        f"/api/v1/correspondence/{correspondence_id}",
        json={"cc_recipients": "Procurement, QA"},
        headers=headers,
    )
    assert update_cc.status_code == 200, update_cc.text
    assert (update_cc.json().get("data") or {}).get("cc_recipients") == "Procurement, QA"

    document_id, doc_no, transmittal_no = _seed_document_and_transmittal(project_code, discipline_code)
    document_relation = client.post(
        f"/api/v1/correspondence/{correspondence_id}/relations",
        json={"target_entity_type": "document", "target_code": doc_no, "relation_type": "references"},
        headers=headers,
    )
    assert document_relation.status_code == 200, document_relation.text
    assert (document_relation.json().get("data") or {}).get("target_entity_type") == "document"

    attachment_relation = client.post(
        f"/api/v1/correspondence/{correspondence_id}/relations",
        json={"target_entity_type": "document", "target_code": doc_no, "relation_type": "attachment"},
        headers=headers,
    )
    assert attachment_relation.status_code == 200, attachment_relation.text
    assert (attachment_relation.json().get("data") or {}).get("relation_type") == "attachment"

    transmittal_relation = client.post(
        f"/api/v1/correspondence/{correspondence_id}/relations",
        json={"target_entity_type": "transmittal", "target_code": transmittal_no, "relation_type": "related"},
        headers=headers,
    )
    assert transmittal_relation.status_code == 200, transmittal_relation.text
    assert (transmittal_relation.json().get("data") or {}).get("target_entity_type") == "transmittal"
    transmittal_relation_id = str((transmittal_relation.json().get("data") or {}).get("id") or "")
    assert transmittal_relation_id.startswith("external:")

    meeting_res = client.post(
        "/api/v1/meeting-minutes/create",
        json={
            "title": "Correspondence reciprocal meeting",
            "project_code": project_code,
            "meeting_date": datetime.utcnow().isoformat(),
            "status": "Open",
        },
        headers=headers,
    )
    assert meeting_res.status_code == 200, meeting_res.text
    meeting = meeting_res.json().get("data") or {}
    meeting_id = int(meeting.get("id") or 0)
    meeting_no = str(meeting.get("meeting_no") or "")
    assert meeting_id > 0 and meeting_no
    meeting_relation = client.post(
        f"/api/v1/correspondence/{correspondence_id}/relations",
        json={"target_entity_type": "meeting_minute", "target_code": meeting_no, "relation_type": "references"},
        headers=headers,
    )
    assert meeting_relation.status_code == 200, meeting_relation.text
    assert (meeting_relation.json().get("data") or {}).get("target_entity_type") == "meeting_minute"

    correspondence_relation = client.post(
        f"/api/v1/correspondence/{correspondence_id}/relations",
        json={"target_entity_type": "correspondence", "target_code": related_reference_no, "relation_type": "references"},
        headers=headers,
    )
    assert correspondence_relation.status_code == 200, correspondence_relation.text
    assert (correspondence_relation.json().get("data") or {}).get("target_entity_type") == "correspondence"
    assert (correspondence_relation.json().get("data") or {}).get("target_code") == related_reference_no

    self_relation = client.post(
        f"/api/v1/correspondence/{correspondence_id}/relations",
        json={"target_entity_type": "correspondence", "target_code": reference_no, "relation_type": "related"},
        headers=headers,
    )
    assert self_relation.status_code == 400, self_relation.text

    relations = client.get(f"/api/v1/correspondence/{correspondence_id}/relations", headers=headers)
    assert relations.status_code == 200, relations.text
    indexed = {
        (str(item.get("target_entity_type") or ""), str(item.get("target_code") or "")): item
        for item in relations.json().get("data") or []
    }
    assert ("document", doc_no) in indexed
    assert any(
        item.get("target_entity_type") == "document"
        and item.get("target_code") == doc_no
        and item.get("relation_type") == "attachment"
        for item in relations.json().get("data") or []
    )
    assert ("transmittal", transmittal_no) in indexed
    assert ("meeting_minute", meeting_no) in indexed
    assert ("correspondence", related_reference_no) in indexed

    related_relations = client.get(f"/api/v1/correspondence/{related_correspondence_id}/relations", headers=headers)
    assert related_relations.status_code == 200, related_relations.text
    related_relation_rows = related_relations.json().get("data") or []
    assert any(
        row.get("target_entity_type") == "correspondence"
        and row.get("target_code") == reference_no
        and row.get("direction") == "incoming"
        for row in related_relation_rows
    )

    correspondence_report = client.get(
        f"/api/v1/correspondence/reports/table?project_code={project_code}&discipline_code={discipline_code}&status=Open",
        headers=headers,
    )
    assert correspondence_report.status_code == 200, correspondence_report.text
    report_body = correspondence_report.json()
    assert report_body.get("ok") is True
    report_rows = report_body.get("data") or []
    assert any(row.get("reference_no") == reference_no for row in report_rows)
    assert any(row.get("reference_no") == related_reference_no for row in report_rows)
    assert int(report_body.get("summary", {}).get("total", 0)) >= 2

    transmittal_detail = client.get(f"/api/v1/transmittal/item/{transmittal_no}", headers=headers)
    assert transmittal_detail.status_code == 200, transmittal_detail.text
    reciprocal = transmittal_detail.json().get("correspondence_relations") or []
    assert any(item.get("reference_no") == reference_no for item in reciprocal)

    meeting_relations = client.get(f"/api/v1/meeting-minutes/{meeting_id}/relations", headers=headers)
    assert meeting_relations.status_code == 200, meeting_relations.text
    incoming_meeting = meeting_relations.json().get("incoming") or []
    assert any(item.get("target_entity_type") == "correspondence" and item.get("target_code") == reference_no for item in incoming_meeting)
    meeting_relation_search = client.get(
        f"/api/v1/meeting-minutes/list?relation_search={reference_no}",
        headers=headers,
    )
    assert meeting_relation_search.status_code == 200, meeting_relation_search.text
    assert any(int(item.get("id") or 0) == meeting_id for item in meeting_relation_search.json().get("data") or [])

    delete_relation = client.delete(
        f"/api/v1/correspondence/{correspondence_id}/relations/{transmittal_relation_id}",
        headers=headers,
    )
    assert delete_relation.status_code == 200, delete_relation.text

    relations_after_delete = client.get(f"/api/v1/correspondence/{correspondence_id}/relations", headers=headers)
    assert relations_after_delete.status_code == 200, relations_after_delete.text
    direct_transmittals = [
        item
        for item in relations_after_delete.json().get("data") or []
        if item.get("target_entity_type") == "transmittal" and not item.get("inferred")
    ]
    assert direct_transmittals == []

    document_detail = client.get(f"/api/v1/archive/documents/{document_id}", headers=headers)
    assert document_detail.status_code == 200, document_detail.text
    outgoing = ((document_detail.json().get("relations") or {}).get("outgoing") or [])
    assert any(
        item.get("target_entity_type") == "correspondence" and item.get("target_code") == reference_no
        for item in outgoing
    )

    transmittal_detail_after_delete = client.get(f"/api/v1/transmittal/item/{transmittal_no}", headers=headers)
    assert transmittal_detail_after_delete.status_code == 200, transmittal_detail_after_delete.text
    assert transmittal_detail_after_delete.json().get("correspondence_relations") == []
