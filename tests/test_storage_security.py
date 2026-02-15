from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import ArchiveFile, DocumentRevision, MdrDocument, Project
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
