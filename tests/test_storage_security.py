from __future__ import annotations

import io
import os
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import (
    ArchiveFile,
    Correspondence,
    CorrespondenceAttachment,
    DocumentRevision,
    MdrDocument,
    OpenProjectLink,
    Project,
)
from app.db.session import engine
from app.main import app
from tests.auth_helpers import get_auth_headers

client = TestClient(app)


@pytest.fixture(scope="module")
def admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _create_test_document() -> tuple[int, str]:
    project_code = f"TS{uuid.uuid4().hex[:6].upper()}"
    doc_number = f"{project_code}-EGN0001-TGEN"
    with Session(engine) as db:
        project = Project(code=project_code, name_e=f"Storage {project_code}", is_active=True)
        db.add(project)
        doc = MdrDocument(
            doc_number=doc_number,
            doc_title_e=f"Storage Test {project_code}",
            subject=f"Storage Test {project_code}",
            project_code=project_code,
            mdr_code="E",
            discipline_code=None,
            package_code=None,
            block="T",
            level_code="GEN",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc.id, project_code


def _delete_test_document(document_id: int, project_code: str) -> None:
    with Session(engine) as db:
        revisions = (
            db.query(DocumentRevision)
            .filter(DocumentRevision.document_id == int(document_id))
            .all()
        )
        revision_ids = [int(row.id) for row in revisions]
        if revision_ids:
            archive_ids = [
                int(row[0])
                for row in db.query(ArchiveFile.id)
                .filter(ArchiveFile.revision_id.in_(revision_ids))
                .all()
            ]
            if archive_ids:
                db.query(OpenProjectLink).filter(
                    OpenProjectLink.entity_type == "archive_file",
                    OpenProjectLink.entity_id.in_(archive_ids),
                ).delete(synchronize_session=False)
            db.query(ArchiveFile).filter(ArchiveFile.revision_id.in_(revision_ids)).delete(
                synchronize_session=False
            )
            db.query(DocumentRevision).filter(DocumentRevision.id.in_(revision_ids)).delete(
                synchronize_session=False
            )
        row = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
        if row:
            db.delete(row)
        project = db.query(Project).filter(Project.code == project_code).first()
        if project:
            db.delete(project)
        db.commit()


def _create_test_correspondence_with_attachment(admin_headers: dict[str, str]) -> tuple[int, str, int]:
    project_code = f"TC{uuid.uuid4().hex[:6].upper()}"
    with Session(engine) as db:
        project = Project(code=project_code, name_e=f"Corr {project_code}", is_active=True)
        db.add(project)
        db.commit()

    create_response = client.post(
        "/api/v1/correspondence/create",
        json={
            "project_code": project_code,
            "issuing_code": project_code,
            "category_code": "CO",
            "doc_type": "Correspondence",
            "direction": "O",
            "reference_no": f"{project_code}-CO-O-2602001",
            "subject": f"Storage attachment {project_code}",
            "status": "Open",
        },
        headers=admin_headers,
    )
    assert create_response.status_code == 200, create_response.text
    correspondence_id = int(create_response.json().get("data", {}).get("id") or 0)
    assert correspondence_id > 0

    upload_response = client.post(
        f"/api/v1/correspondence/{correspondence_id}/attachments/upload",
        data={"file_kind": "attachment"},
        files={"file": ("corr.txt", io.BytesIO(b"corr-attachment-content"), "text/plain")},
        headers=admin_headers,
    )
    assert upload_response.status_code == 200, upload_response.text
    attachment_id = int(upload_response.json().get("data", {}).get("id") or 0)
    assert attachment_id > 0
    return correspondence_id, project_code, attachment_id


def _delete_test_correspondence(correspondence_id: int, project_code: str) -> None:
    stored_paths: list[str] = []
    with Session(engine) as db:
        attachments = (
            db.query(CorrespondenceAttachment)
            .filter(CorrespondenceAttachment.correspondence_id == int(correspondence_id))
            .all()
        )
        stored_paths.extend([str(row.stored_path or "") for row in attachments])
        db.query(OpenProjectLink).filter(
            OpenProjectLink.entity_type == "correspondence_attachment",
            OpenProjectLink.entity_id.in_([int(row.id) for row in attachments]),
        ).delete(synchronize_session=False)

        row = db.query(Correspondence).filter(Correspondence.id == int(correspondence_id)).first()
        if row:
            db.delete(row)
        project = db.query(Project).filter(Project.code == project_code).first()
        if project:
            db.delete(project)
        db.commit()

    for path in stored_paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


def test_upload_rejects_executable_payload_disguised_as_pdf(admin_headers: dict[str, str]) -> None:
    document_id, project_code = _create_test_document()
    try:
        payload = {
            "document_id": str(document_id),
            "revision": "00",
            "status": "IFA",
            "file_kind": "pdf",
        }
        files = {
            "file": ("fake.pdf", io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00EXE"), "application/pdf"),
        }
        response = client.post("/api/v1/archive/upload", data=payload, files=files, headers=admin_headers)
        assert response.status_code == 422, response.text
        assert "Dangerous mime type detected" in response.text or "validation rejected" in response.text.lower()
    finally:
        _delete_test_document(document_id, project_code)


def test_upload_integrity_payload_contains_sha256(admin_headers: dict[str, str]) -> None:
    document_id, project_code = _create_test_document()
    try:
        payload = {
            "document_id": str(document_id),
            "revision": "00",
            "status": "IFA",
            "file_kind": "pdf",
        }
        files = {
            "file": ("safe.pdf", io.BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n"), "application/pdf"),
        }
        upload = client.post("/api/v1/archive/upload", data=payload, files=files, headers=admin_headers)
        assert upload.status_code == 200, upload.text
        body = upload.json()
        file_id = int(body.get("file_id") or 0)
        assert file_id > 0
        assert str(body.get("sha256") or "").strip()
        assert body.get("validation_status") in {"valid", "warning"}

        integrity = client.get(f"/api/v1/archive/files/{file_id}/integrity", headers=admin_headers)
        assert integrity.status_code == 200, integrity.text
        check = integrity.json()
        assert check.get("sha256") == body.get("sha256")
        assert check.get("validation_status") == body.get("validation_status")
    finally:
        _delete_test_document(document_id, project_code)


def test_local_cache_pin_manifest_unpin_flow(admin_headers: dict[str, str]) -> None:
    document_id, project_code = _create_test_document()
    try:
        upload = client.post(
            "/api/v1/archive/upload",
            data={
                "document_id": str(document_id),
                "revision": "00",
                "status": "IFA",
                "file_kind": "pdf",
            },
            files={"file": ("pin.pdf", io.BytesIO(b"%PDF-1.4\npin\n"), "application/pdf")},
            headers=admin_headers,
        )
        assert upload.status_code == 200, upload.text
        file_id = int(upload.json().get("file_id") or 0)
        assert file_id > 0

        pin = client.post(
            "/api/v1/storage/local-cache/pin",
            json={"file_id": file_id},
            headers=admin_headers,
        )
        assert pin.status_code == 200, pin.text
        assert pin.json().get("ok") is True

        manifest = client.get("/api/v1/storage/local-cache/manifest", headers=admin_headers)
        assert manifest.status_code == 200, manifest.text
        items = manifest.json().get("items", [])
        assert any(int(item.get("file_id", 0)) == file_id for item in items)

        unpin = client.post(
            "/api/v1/storage/local-cache/unpin",
            json={"file_id": file_id},
            headers=admin_headers,
        )
        assert unpin.status_code == 200, unpin.text
        assert unpin.json().get("ok") is True
    finally:
        _delete_test_document(document_id, project_code)


def test_openproject_status_contract_for_archive_and_correspondence(
    admin_headers: dict[str, str],
) -> None:
    document_id, project_code = _create_test_document()
    correspondence_id = 0
    correspondence_project = ""
    archive_file_id = 0
    attachment_id = 0
    try:
        upload = client.post(
            "/api/v1/archive/upload",
            data={
                "document_id": str(document_id),
                "revision": "00",
                "status": "IFA",
                "file_kind": "pdf",
            },
            files={"file": ("status.pdf", io.BytesIO(b"%PDF-1.4\nstatus\n"), "application/pdf")},
            headers=admin_headers,
        )
        assert upload.status_code == 200, upload.text
        archive_file_id = int(upload.json().get("file_id") or 0)
        assert archive_file_id > 0

        correspondence_id, correspondence_project, attachment_id = _create_test_correspondence_with_attachment(
            admin_headers
        )

        with Session(engine) as db:
            db.add(
                OpenProjectLink(
                    entity_type="archive_file",
                    entity_id=archive_file_id,
                    work_package_id=321,
                    openproject_attachment_id="987",
                    sync_status="synced",
                    last_synced_at=datetime.utcnow(),
                )
            )
            db.add(
                OpenProjectLink(
                    entity_type="correspondence_attachment",
                    entity_id=attachment_id,
                    work_package_id=654,
                    openproject_attachment_id="654321",
                    sync_status="failed",
                    last_synced_at=datetime.utcnow(),
                )
            )
            db.commit()

        status_response = client.post(
            "/api/v1/storage/openproject/status",
            json={
                "items": [
                    {"entity_type": "archive_file", "entity_id": archive_file_id},
                    {
                        "entity_type": "correspondence_attachment",
                        "entity_id": attachment_id,
                    },
                ]
            },
            headers=admin_headers,
        )
        assert status_response.status_code == 200, status_response.text
        payload = status_response.json()
        assert payload.get("ok") is True
        rows = payload.get("items") or []
        indexed = {
            (str(row.get("entity_type")), int(row.get("entity_id") or 0)): row for row in rows
        }

        archive_row = indexed.get(("archive_file", archive_file_id))
        assert archive_row is not None
        assert archive_row.get("sync_status") == "synced"
        assert int(archive_row.get("work_package_id") or 0) == 321
        assert str(archive_row.get("openproject_attachment_id") or "") == "987"
        assert archive_row.get("last_synced_at")

        attachment_row = indexed.get(("correspondence_attachment", attachment_id))
        assert attachment_row is not None
        assert attachment_row.get("sync_status") == "failed"
        assert int(attachment_row.get("work_package_id") or 0) == 654
        assert str(attachment_row.get("openproject_attachment_id") or "") == "654321"
        assert attachment_row.get("last_synced_at")
    finally:
        if correspondence_id and correspondence_project:
            _delete_test_correspondence(correspondence_id, correspondence_project)
        _delete_test_document(document_id, project_code)
