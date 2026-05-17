import io
import uuid
import zipfile
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.models import (
    ArchiveFile,
    ArchiveFilePublicShare,
    Discipline,
    DocumentRevision,
    MdrDocument,
    Organization,
    Transmittal,
    TransmittalDoc,
)
from app.db.session import SessionLocal
from app.main import app
from app.services import archive_service as archive_service_module
from tests.auth_helpers import get_auth_headers
from tests.auth_helpers import get_test_admin_credentials
from tests.site_logs_helpers import create_scoped_user_and_login, ensure_project_discipline

client = TestClient(app)
API_PREFIX = "/api/v1"


def _auth_headers() -> dict:
    return get_auth_headers(client)


def test_archive_list_requires_auth():
    response = client.get("/api/v1/archive/list")
    assert response.status_code in (401, 403)


def test_dashboard_table_works_with_auth():
    headers = _auth_headers()
    response = client.get("/api/v1/dashboard/table", headers=headers)
    assert response.status_code == 200, response.text

    body = response.json()
    assert "items" in body
    assert isinstance(body["items"], list)

    if body["items"]:
        first = body["items"][0]
        for key in ("id", "doc_number", "status", "revision", "created_at"):
            assert key in first


def test_transmittal_create_and_list_work_with_current_model():
    headers = _auth_headers()
    payload = {
        "project_code": "T202",
        "sender": "O",
        "receiver": "C",
        "subject": f"t-{uuid.uuid4().hex[:6]}",
        "notes": "",
        "documents": [],
    }

    create_response = client.post(
        "/api/v1/transmittal/create",
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
    )
    assert create_response.status_code == 200, create_response.text
    created_no = create_response.json()["transmittal_no"]

    list_response = client.get("/api/v1/transmittal/", headers=headers)
    assert list_response.status_code == 200, list_response.text
    items = list_response.json()
    assert any(item.get("transmittal_no") == created_no for item in items)


def test_transmittal_download_cover_returns_pdf_attachment():
    headers = _auth_headers()
    project_code, discipline_code = ensure_project_discipline(client, headers)
    doc_number = f"{project_code}-PDF-{uuid.uuid4().hex[:6].upper()}-TGEN"
    document_id = 0
    revision_id = 0
    archive_file_id = 0

    with SessionLocal() as db:
        document = MdrDocument(
            doc_number=doc_number,
            doc_title_e="Transmittal PDF Test Document",
            doc_title_p="Transmittal PDF Test Document",
            subject="Transmittal PDF Test Document",
            project_code=project_code,
            discipline_code=discipline_code,
            mdr_code="E",
            package_code=None,
            block="T",
            level_code=None,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        document_id = int(document.id or 0)
        revision = DocumentRevision(
            document_id=document_id,
            revision="00",
            status="IFA",
            file_name=f"{doc_number}.pdf",
            file_path=f"webdav://Archive/{doc_number}.pdf",
        )
        db.add(revision)
        db.flush()
        revision_id = int(revision.id or 0)
        archive_file = ArchiveFile(
            revision_id=revision_id,
            original_name=f"{doc_number}.pdf",
            stored_path=f"webdav://Archive/{doc_number}.pdf",
            mime_type="application/pdf",
            detected_mime="application/pdf",
            size_bytes=2048,
            storage_backend="nextcloud",
            file_kind="pdf",
            is_primary=True,
            revision="00",
            status="IFA",
        )
        db.add(archive_file)
        db.flush()
        archive_file_id = int(archive_file.id or 0)
        share_url = f"https://cloud.example.test/s/{uuid.uuid4().hex}"
        db.add(
            ArchiveFilePublicShare(
                file_id=archive_file_id,
                provider="nextcloud",
                provider_share_id=f"share-{uuid.uuid4().hex[:8]}",
                share_url=share_url,
                resolved_path=f"/Archive/{doc_number}.pdf",
                source="primary_nextcloud",
                permissions=1,
                password_set=False,
                expires_at=datetime.utcnow() + timedelta(days=30),
            )
        )
        db.commit()

    payload = {
        "project_code": project_code,
        "sender": "O",
        "receiver": "C",
        "subject": f"pdf-{uuid.uuid4().hex[:6]}",
        "notes": "",
        "documents": [
            {
                "document_code": doc_number,
                "revision": "00",
                "status": "IFA",
                "electronic_copy": True,
                "hard_copy": False,
            }
        ],
    }

    try:
        create_response = client.post(
            "/api/v1/transmittal/create",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )
        assert create_response.status_code == 200, create_response.text
        transmittal_no = create_response.json()["transmittal_no"]

        preview_response = client.get(f"/api/v1/transmittal/{transmittal_no}/print-preview", headers=headers)
        assert preview_response.status_code == 200, preview_response.text
        assert preview_response.headers.get("content-type", "").startswith("text/html")
        assert "برگه ارسال مدارک" in preview_response.text
        assert transmittal_no in preview_response.text
        assert doc_number in preview_response.text
        assert share_url in preview_response.text
        assert f'href="{share_url}"' in preview_response.text

        pdf_response = client.get(f"/api/v1/transmittal/{transmittal_no}/download-cover", headers=headers)
        assert pdf_response.status_code == 200, pdf_response.text
        assert pdf_response.headers.get("content-type", "").startswith("application/pdf")
        disposition = pdf_response.headers.get("content-disposition", "").lower()
        assert "attachment" in disposition
        assert transmittal_no.lower() in disposition
        assert pdf_response.content.startswith(b"%PDF")
        assert len(pdf_response.content) > 1000
    finally:
        with SessionLocal() as db:
            if archive_file_id > 0:
                db.query(ArchiveFilePublicShare).filter(ArchiveFilePublicShare.file_id == archive_file_id).delete(
                    synchronize_session=False
                )
                db.query(ArchiveFile).filter(ArchiveFile.id == archive_file_id).delete(synchronize_session=False)
            if revision_id > 0:
                db.query(DocumentRevision).filter(DocumentRevision.id == revision_id).delete(synchronize_session=False)
            if document_id > 0:
                document = db.query(MdrDocument).filter(MdrDocument.id == document_id).first()
                if document is not None:
                    db.delete(document)
            db.commit()


def test_transmittal_e_copy_auto_creates_pdf_and_native_public_links(monkeypatch):
    headers = _auth_headers()
    project_code, discipline_code = ensure_project_discipline(client, headers)
    doc_number = f"{project_code}-AUTO-SHARE-{uuid.uuid4().hex[:6].upper()}-TGEN"
    document_id = 0
    revision_id = 0
    archive_file_ids: list[int] = []

    class FakeNextcloudShareAdapter:
        def __init__(self) -> None:
            self.create_calls: list[str] = []

        def file_exists(self, remote_path: str) -> bool:
            return True

        def create_public_share(self, remote_relative_path: str, **kwargs):
            del kwargs
            self.create_calls.append(remote_relative_path)
            suffix = remote_relative_path.strip("/").replace("/", "-").replace(".", "-")
            return {
                "provider_share_id": f"share-{len(self.create_calls)}",
                "token": f"token-{len(self.create_calls)}",
                "url": f"https://cloud.example.test/s/{suffix}",
            }

    adapter = FakeNextcloudShareAdapter()
    monkeypatch.setattr(archive_service_module, "_nextcloud_adapter", lambda _db: adapter)

    with SessionLocal() as db:
        document = MdrDocument(
            doc_number=doc_number,
            doc_title_e="Auto Share Native Test",
            doc_title_p="Auto Share Native Test",
            subject="Auto Share Native Test",
            project_code=project_code,
            discipline_code=discipline_code,
            mdr_code="E",
            package_code=None,
            block="T",
            level_code=None,
        )
        db.add(document)
        db.flush()
        document_id = int(document.id or 0)
        revision = DocumentRevision(
            document_id=document_id,
            revision="00",
            status="IFA",
            file_name=f"{doc_number}.pdf",
            file_path=f"webdav://Archive/{doc_number}.pdf",
        )
        db.add(revision)
        db.flush()
        revision_id = int(revision.id or 0)
        for file_kind, ext, mime in (
            ("pdf", "pdf", "application/pdf"),
            ("native", "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ):
            archive_file = ArchiveFile(
                revision_id=revision_id,
                original_name=f"{doc_number}.{ext}",
                stored_path=f"webdav://Archive/{doc_number}.{ext}",
                mime_type=mime,
                detected_mime=mime,
                size_bytes=2048,
                storage_backend="nextcloud",
                file_kind=file_kind,
                is_primary=file_kind == "pdf",
                revision="00",
                status="IFA",
            )
            db.add(archive_file)
            db.flush()
            archive_file_ids.append(int(archive_file.id or 0))
        db.commit()

    transmittal_no = ""
    try:
        create_response = client.post(
            "/api/v1/transmittal/create",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "project_code": project_code,
                "sender": "O",
                "receiver": "C",
                "subject": f"auto-share-{uuid.uuid4().hex[:6]}",
                "notes": "",
                "documents": [
                    {
                        "document_code": doc_number,
                        "revision": "00",
                        "status": "IFA",
                        "file_kind": "pdf",
                        "electronic_copy": True,
                        "hard_copy": False,
                    },
                    {
                        "document_code": doc_number,
                        "revision": "00",
                        "status": "IFA",
                        "file_kind": "native",
                        "electronic_copy": True,
                        "hard_copy": False,
                    },
                ],
            },
        )
        assert create_response.status_code == 200, create_response.text
        transmittal_no = create_response.json()["transmittal_no"]
        assert sorted(adapter.create_calls) == sorted([f"/Archive/{doc_number}.pdf", f"/Archive/{doc_number}.xlsx"])

        preview_response = client.get(f"/api/v1/transmittal/{transmittal_no}/print-preview", headers=headers)
        assert preview_response.status_code == 200, preview_response.text
        assert f"https://cloud.example.test/s/Archive-{doc_number}-pdf" in preview_response.text
        assert f"https://cloud.example.test/s/Archive-{doc_number}-xlsx" in preview_response.text
        assert "Native" in preview_response.text

        with SessionLocal() as db:
            shares = (
                db.query(ArchiveFilePublicShare)
                .filter(ArchiveFilePublicShare.file_id.in_(archive_file_ids))
                .all()
            )
            assert len(shares) == 2

            db.query(ArchiveFilePublicShare).filter(ArchiveFilePublicShare.file_id.in_(archive_file_ids)).delete(
                synchronize_session=False
            )
            db.commit()

        adapter.create_calls.clear()
        preview_retry_response = client.get(f"/api/v1/transmittal/{transmittal_no}/print-preview", headers=headers)
        assert preview_retry_response.status_code == 200, preview_retry_response.text
        assert sorted(adapter.create_calls) == sorted([f"/Archive/{doc_number}.pdf", f"/Archive/{doc_number}.xlsx"])
        assert f"https://cloud.example.test/s/Archive-{doc_number}-pdf" in preview_retry_response.text
        assert f"https://cloud.example.test/s/Archive-{doc_number}-xlsx" in preview_retry_response.text
    finally:
        with SessionLocal() as db:
            if transmittal_no:
                db.query(TransmittalDoc).filter(TransmittalDoc.transmittal_id == transmittal_no).delete(
                    synchronize_session=False
                )
                db.query(Transmittal).filter(Transmittal.id == transmittal_no).delete(synchronize_session=False)
            if archive_file_ids:
                db.query(ArchiveFilePublicShare).filter(ArchiveFilePublicShare.file_id.in_(archive_file_ids)).delete(
                    synchronize_session=False
                )
                db.query(ArchiveFile).filter(ArchiveFile.id.in_(archive_file_ids)).delete(synchronize_session=False)
            if revision_id > 0:
                db.query(DocumentRevision).filter(DocumentRevision.id == revision_id).delete(synchronize_session=False)
            if document_id > 0:
                document = db.query(MdrDocument).filter(MdrDocument.id == document_id).first()
                if document is not None:
                    db.delete(document)
            db.commit()


def test_transmittal_download_package_zip_contains_cover_manifest_and_files(tmp_path):
    headers = _auth_headers()
    project_code, discipline_code = ensure_project_discipline(client, headers)
    doc_number = f"{project_code}-PKG-{uuid.uuid4().hex[:6].upper()}-TGEN"
    pdf_path = tmp_path / f"{doc_number}.pdf"
    native_path = tmp_path / f"{doc_number}.xlsx"
    pdf_payload = b"%PDF-1.4\n%package-test-pdf\n"
    native_payload = b"native-editable-package-test"
    pdf_path.write_bytes(pdf_payload)
    native_path.write_bytes(native_payload)

    created_transmittal_no = ""
    document_id = 0
    revision_id = 0
    archive_file_ids: list[int] = []

    with SessionLocal() as db:
        document = MdrDocument(
            doc_number=doc_number,
            doc_title_e="Transmittal Package Test Document",
            doc_title_p="Transmittal Package Test Document",
            subject="Transmittal Package Test Document",
            project_code=project_code,
            discipline_code=discipline_code,
            mdr_code="E",
            package_code=None,
            block="T",
            level_code=None,
        )
        db.add(document)
        db.flush()
        document_id = int(document.id or 0)
        revision = DocumentRevision(
            document_id=document_id,
            revision="00",
            status="IFA",
            file_name=pdf_path.name,
            file_path=str(pdf_path),
        )
        db.add(revision)
        db.flush()
        revision_id = int(revision.id or 0)
        for file_kind, path, mime in (
            ("pdf", pdf_path, "application/pdf"),
            ("native", native_path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ):
            archive_file = ArchiveFile(
                revision_id=revision_id,
                original_name=path.name,
                stored_path=str(path),
                mime_type=mime,
                detected_mime=mime,
                size_bytes=path.stat().st_size,
                storage_backend="local",
                file_kind=file_kind,
                is_primary=True,
                revision="00",
                status="IFA",
            )
            db.add(archive_file)
            db.flush()
            archive_file_ids.append(int(archive_file.id or 0))
        db.commit()

    try:
        create_response = client.post(
            "/api/v1/transmittal/create",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "project_code": project_code,
                "sender": "O",
                "receiver": "C",
                "subject": f"package-{uuid.uuid4().hex[:6]}",
                "notes": "",
                "documents": [
                    {
                        "document_code": doc_number,
                        "revision": "00",
                        "status": "IFA",
                        "file_kind": "pdf",
                        "remarks": "PDF package copy",
                        "electronic_copy": True,
                        "hard_copy": False,
                    },
                    {
                        "document_code": doc_number,
                        "revision": "00",
                        "status": "IFA",
                        "file_kind": "native",
                        "remarks": "Native package copy",
                        "electronic_copy": True,
                        "hard_copy": False,
                    },
                ],
            },
        )
        assert create_response.status_code == 200, create_response.text
        created_transmittal_no = create_response.json()["transmittal_no"]

        package_response = client.get(
            f"/api/v1/transmittal/{created_transmittal_no}/download-package",
            headers=headers,
        )
        assert package_response.status_code == 200, package_response.text
        assert package_response.headers.get("content-type", "").startswith("application/zip")
        disposition = package_response.headers.get("content-disposition", "").lower()
        assert "attachment" in disposition
        assert created_transmittal_no.lower() in disposition

        with zipfile.ZipFile(io.BytesIO(package_response.content)) as package_zip:
            names = package_zip.namelist()
            assert any(name.endswith(".pdf") and "/00_Cover/" in name for name in names)
            pdf_entry = next(name for name in names if "/01_Documents/PDF/" in name and name.endswith(".pdf"))
            native_entry = next(name for name in names if "/01_Documents/Native/" in name and name.endswith(".xlsx"))
            manifest_entry = next(name for name in names if name.endswith("/manifest.csv"))
            assert package_zip.read(pdf_entry) == pdf_payload
            assert package_zip.read(native_entry) == native_payload
            manifest_text = package_zip.read(manifest_entry).decode("utf-8-sig")
            assert doc_number in manifest_text
            assert "PDF package copy" in manifest_text
            assert "Native package copy" in manifest_text
            assert manifest_text.count("included") == 2
    finally:
        with SessionLocal() as db:
            if created_transmittal_no:
                db.query(TransmittalDoc).filter(TransmittalDoc.transmittal_id == created_transmittal_no).delete(
                    synchronize_session=False
                )
                db.query(Transmittal).filter(Transmittal.id == created_transmittal_no).delete(
                    synchronize_session=False
                )
            if archive_file_ids:
                db.query(ArchiveFile).filter(ArchiveFile.id.in_(archive_file_ids)).delete(synchronize_session=False)
            if revision_id > 0:
                db.query(DocumentRevision).filter(DocumentRevision.id == revision_id).delete(synchronize_session=False)
            if document_id > 0:
                db.query(MdrDocument).filter(MdrDocument.id == document_id).delete(synchronize_session=False)
            db.commit()


def test_transmittal_document_file_kind_options_and_validation():
    headers = _auth_headers()
    project_code, discipline_code = ensure_project_discipline(client, headers)
    dual_doc_number = f"{project_code}-DUAL-{uuid.uuid4().hex[:6].upper()}-TGEN"
    pdf_doc_number = f"{project_code}-PDFONLY-{uuid.uuid4().hex[:6].upper()}-TGEN"
    native_doc_number = f"{project_code}-NATIVEONLY-{uuid.uuid4().hex[:6].upper()}-TGEN"
    created_transmittal_no = ""
    document_ids: list[int] = []
    revision_ids: list[int] = []
    archive_file_ids: list[int] = []
    share_urls: dict[str, str] = {}

    with SessionLocal() as db:
        for doc_number, file_kinds in (
            (dual_doc_number, ("pdf", "native")),
            (pdf_doc_number, ("pdf",)),
            (native_doc_number, ("native",)),
        ):
            first_kind = file_kinds[0]
            first_ext = "xlsx" if first_kind == "native" else "pdf"
            document = MdrDocument(
                doc_number=doc_number,
                doc_title_e=f"Transmittal File Kind {doc_number}",
                doc_title_p=f"Transmittal File Kind {doc_number}",
                subject=f"Transmittal File Kind {doc_number}",
                project_code=project_code,
                discipline_code=discipline_code,
                mdr_code="E",
                package_code=None,
                block="T",
                level_code=None,
            )
            db.add(document)
            db.flush()
            document_ids.append(int(document.id or 0))
            revision = DocumentRevision(
                document_id=int(document.id or 0),
                revision="00",
                status="IFA",
                file_name=f"{doc_number}.{first_ext}",
                file_path=f"local://Archive/{doc_number}.{first_ext}",
            )
            db.add(revision)
            db.flush()
            revision_ids.append(int(revision.id or 0))
            for file_kind in file_kinds:
                ext = "xlsx" if file_kind == "native" else "pdf"
                mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if file_kind == "native" else "application/pdf"
                archive_file = ArchiveFile(
                    revision_id=int(revision.id or 0),
                    original_name=f"{doc_number}.{ext}",
                    stored_path=f"local://Archive/{doc_number}.{ext}",
                    mime_type=mime,
                    detected_mime=mime,
                    size_bytes=2048 if file_kind == "native" else 1024,
                    storage_backend="local",
                    file_kind=file_kind,
                    is_primary=True,
                    revision="00",
                    status="IFA",
                )
                db.add(archive_file)
                db.flush()
                archive_file_ids.append(int(archive_file.id or 0))
                share_url = f"https://cloud.example.test/s/{uuid.uuid4().hex}"
                share_urls[f"{doc_number}:{file_kind}"] = share_url
                db.add(
                    ArchiveFilePublicShare(
                        file_id=int(archive_file.id or 0),
                        provider="nextcloud",
                        provider_share_id=f"share-{uuid.uuid4().hex[:8]}",
                        share_url=share_url,
                        resolved_path=f"/Archive/{doc_number}.{ext}",
                        source="primary_nextcloud",
                        permissions=1,
                        password_set=False,
                        expires_at=datetime.utcnow() + timedelta(days=30),
                    )
                )
        db.commit()

    try:
        eligible_response = client.get(
            "/api/v1/transmittal/eligible-docs",
            params={"project_code": project_code, "q": dual_doc_number},
            headers=headers,
        )
        assert eligible_response.status_code == 200, eligible_response.text
        row = next(item for item in eligible_response.json() if item.get("doc_number") == dual_doc_number)
        assert row.get("default_file_kind") == "pdf"
        assert {item.get("value") for item in row.get("file_options") or []} == {"pdf", "native"}

        pdf_only_response = client.get(
            "/api/v1/transmittal/eligible-docs",
            params={"project_code": project_code, "q": pdf_doc_number},
            headers=headers,
        )
        assert pdf_only_response.status_code == 200, pdf_only_response.text
        pdf_only_row = next(item for item in pdf_only_response.json() if item.get("doc_number") == pdf_doc_number)
        assert {item.get("value") for item in pdf_only_row.get("file_options") or []} == {"pdf"}

        native_only_response = client.get(
            "/api/v1/transmittal/eligible-docs",
            params={"project_code": project_code, "q": native_doc_number},
            headers=headers,
        )
        assert native_only_response.status_code == 200, native_only_response.text
        native_only_row = next(
            item for item in native_only_response.json() if item.get("doc_number") == native_doc_number
        )
        assert {item.get("value") for item in native_only_row.get("file_options") or []} == {"native"}

        create_response = client.post(
            "/api/v1/transmittal/create",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "project_code": project_code,
                "sender": "O",
                "receiver": "C",
                "subject": f"file-kind-{uuid.uuid4().hex[:6]}",
                "notes": "",
                "documents": [
                    {
                        "document_code": dual_doc_number,
                        "revision": "00",
                        "status": "IFA",
                        "file_kind": "pdf",
                        "remarks": "PDF issue copy",
                        "electronic_copy": True,
                        "hard_copy": False,
                    },
                    {
                        "document_code": dual_doc_number,
                        "revision": "00",
                        "status": "IFA",
                        "file_kind": "native",
                        "remarks": "Native editable copy",
                        "electronic_copy": True,
                        "hard_copy": False,
                    }
                ],
            },
        )
        assert create_response.status_code == 200, create_response.text
        created_transmittal_no = create_response.json()["transmittal_no"]

        detail_response = client.get(f"/api/v1/transmittal/item/{created_transmittal_no}", headers=headers)
        assert detail_response.status_code == 200, detail_response.text
        detail_docs = detail_response.json().get("documents") or []
        indexed_detail_docs = {item.get("file_kind"): item for item in detail_docs}
        assert set(indexed_detail_docs.keys()) == {"pdf", "native"}
        assert indexed_detail_docs["pdf"].get("file_label") == "PDF"
        assert indexed_detail_docs["native"].get("file_label") == "Native"
        assert indexed_detail_docs["pdf"].get("remarks") == "PDF issue copy"
        assert indexed_detail_docs["native"].get("remarks") == "Native editable copy"

        preview_response = client.get(f"/api/v1/transmittal/{created_transmittal_no}/print-preview", headers=headers)
        assert preview_response.status_code == 200, preview_response.text
        assert "PDF" in preview_response.text
        assert "Native" in preview_response.text
        assert "PDF issue copy" in preview_response.text
        assert "Native editable copy" in preview_response.text
        assert share_urls[f"{dual_doc_number}:pdf"] in preview_response.text
        assert share_urls[f"{dual_doc_number}:native"] in preview_response.text

        duplicate_response = client.post(
            "/api/v1/transmittal/create",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "project_code": project_code,
                "sender": "O",
                "receiver": "C",
                "subject": f"duplicate-kind-{uuid.uuid4().hex[:6]}",
                "notes": "",
                "documents": [
                    {
                        "document_code": dual_doc_number,
                        "revision": "00",
                        "status": "IFA",
                        "file_kind": "pdf",
                        "electronic_copy": True,
                        "hard_copy": False,
                    },
                    {
                        "document_code": dual_doc_number,
                        "revision": "00",
                        "status": "IFA",
                        "file_kind": "pdf",
                        "electronic_copy": True,
                        "hard_copy": False,
                    },
                ],
            },
        )
        assert duplicate_response.status_code == 400, duplicate_response.text
        assert "Duplicate document_code and file_kind" in duplicate_response.text

        invalid_response = client.post(
            "/api/v1/transmittal/create",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "project_code": project_code,
                "sender": "O",
                "receiver": "C",
                "subject": f"invalid-kind-{uuid.uuid4().hex[:6]}",
                "notes": "",
                "documents": [
                    {
                        "document_code": pdf_doc_number,
                        "revision": "00",
                        "status": "IFA",
                        "file_kind": "native",
                        "electronic_copy": True,
                        "hard_copy": False,
                    }
                ],
            },
        )
        assert invalid_response.status_code == 400, invalid_response.text
        assert "not available" in invalid_response.text

        invalid_pdf_response = client.post(
            "/api/v1/transmittal/create",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "project_code": project_code,
                "sender": "O",
                "receiver": "C",
                "subject": f"invalid-pdf-{uuid.uuid4().hex[:6]}",
                "notes": "",
                "documents": [
                    {
                        "document_code": native_doc_number,
                        "revision": "00",
                        "status": "IFA",
                        "file_kind": "pdf",
                        "electronic_copy": True,
                        "hard_copy": False,
                    }
                ],
            },
        )
        assert invalid_pdf_response.status_code == 400, invalid_pdf_response.text
        assert "not available" in invalid_pdf_response.text
    finally:
        with SessionLocal() as db:
            if created_transmittal_no:
                db.query(TransmittalDoc).filter(TransmittalDoc.transmittal_id == created_transmittal_no).delete(
                    synchronize_session=False
                )
                db.query(Transmittal).filter(Transmittal.id == created_transmittal_no).delete(
                    synchronize_session=False
                )
            if archive_file_ids:
                db.query(ArchiveFilePublicShare).filter(ArchiveFilePublicShare.file_id.in_(archive_file_ids)).delete(
                    synchronize_session=False
                )
                db.query(ArchiveFile).filter(ArchiveFile.id.in_(archive_file_ids)).delete(synchronize_session=False)
            if revision_ids:
                db.query(DocumentRevision).filter(DocumentRevision.id.in_(revision_ids)).delete(synchronize_session=False)
            if document_ids:
                db.query(MdrDocument).filter(MdrDocument.id.in_(document_ids)).delete(synchronize_session=False)
            db.commit()


def test_transmittal_eligible_docs_accepts_multiple_disciplines():
    headers = _auth_headers()
    project_code, first_discipline = ensure_project_discipline(client, headers)
    second_discipline = f"MD{uuid.uuid4().hex[:5].upper()}"
    marker = f"MULTIDISC-{uuid.uuid4().hex[:6].upper()}"
    first_doc = f"{project_code}-{marker}-A-TGEN"
    second_doc = f"{project_code}-{marker}-B-TGEN"
    document_ids: list[int] = []
    revision_ids: list[int] = []

    with SessionLocal() as db:
        if db.query(Discipline).filter(Discipline.code == second_discipline).first() is None:
            db.add(
                Discipline(
                    code=second_discipline,
                    name_e=f"Discipline {second_discipline}",
                    name_p=f"Discipline {second_discipline}",
                )
            )
            db.flush()
        for doc_number, discipline in ((first_doc, first_discipline), (second_doc, second_discipline)):
            document = MdrDocument(
                doc_number=doc_number,
                doc_title_e=f"{marker} {discipline}",
                doc_title_p=f"{marker} {discipline}",
                subject=f"{marker} {discipline}",
                project_code=project_code,
                discipline_code=discipline,
                mdr_code="E",
                package_code=None,
                block="T",
                level_code=None,
            )
            db.add(document)
            db.flush()
            document_ids.append(int(document.id or 0))
            revision = DocumentRevision(
                document_id=int(document.id or 0),
                revision="00",
                status="IFA",
                file_name=f"{doc_number}.pdf",
                file_path=f"local://Archive/{doc_number}.pdf",
            )
            db.add(revision)
            db.flush()
            revision_ids.append(int(revision.id or 0))
        db.commit()

    try:
        single_response = client.get(
            "/api/v1/transmittal/eligible-docs",
            params={"project_code": project_code, "discipline_code": first_discipline, "q": marker},
            headers=headers,
        )
        assert single_response.status_code == 200, single_response.text
        assert {item.get("doc_number") for item in single_response.json()} == {first_doc}

        multi_response = client.get(
            "/api/v1/transmittal/eligible-docs",
            params={
                "project_code": project_code,
                "discipline_code": f"{first_discipline},{second_discipline}",
                "q": marker,
            },
            headers=headers,
        )
        assert multi_response.status_code == 200, multi_response.text
        assert {item.get("doc_number") for item in multi_response.json()} == {first_doc, second_doc}
    finally:
        with SessionLocal() as db:
            if revision_ids:
                db.query(DocumentRevision).filter(DocumentRevision.id.in_(revision_ids)).delete(synchronize_session=False)
            if document_ids:
                db.query(MdrDocument).filter(MdrDocument.id.in_(document_ids)).delete(synchronize_session=False)
            db.query(Discipline).filter(Discipline.code == second_discipline).delete(synchronize_session=False)
            db.commit()


def test_transmittal_options_settings_and_labels():
    headers = _auth_headers()
    org_code = f"TRORG{uuid.uuid4().hex[:6].upper()}"
    org_label = f"{org_code} - Transmittal Counterparty"
    with SessionLocal() as db:
        db.add(
            Organization(
                code=org_code,
                name="Transmittal Counterparty",
                org_type="consultant",
                is_active=True,
            )
        )
        db.commit()

    settings_payload = {
        "direction_options": [
            {"code": "O", "label": "صادره", "is_active": True, "sort_order": 10},
            {"code": "I", "label": "وارده", "is_active": True, "sort_order": 20},
        ],
        "recipient_options": [
            {"code": "C", "label": "مشاور", "is_active": True, "sort_order": 10},
        ],
    }
    save_response = client.post(
        "/api/v1/settings/transmittal-parties",
        headers={**headers, "Content-Type": "application/json"},
        json=settings_payload,
    )
    assert save_response.status_code == 200, save_response.text

    options_response = client.get("/api/v1/transmittal/options", headers=headers)
    assert options_response.status_code == 200, options_response.text
    options = options_response.json()
    assert options["direction_options"][0]["label"] == "صادره"
    assert options["recipient_options"][0]["label"] == "مشاور"
    assert any(
        item.get("code") == org_code and item.get("label") == org_label and item.get("source") == "organization"
        for item in options["recipient_options"]
    )
    assert any(
        item.get("code") == org_code and item.get("label") == org_label and item.get("source") == "organization"
        for item in options["sender_options"]
    )

    payload = {
        "project_code": "T202",
        "sender": org_code,
        "receiver": "C",
        "direction": "O",
        "subject": f"labels-{uuid.uuid4().hex[:6]}",
        "notes": "",
        "documents": [],
    }
    create_response = client.post(
        "/api/v1/transmittal/create",
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
    )
    assert create_response.status_code == 200, create_response.text
    transmittal_no = create_response.json()["transmittal_no"]

    detail_response = client.get(f"/api/v1/transmittal/item/{transmittal_no}", headers=headers)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["sender_label"] == org_label
    assert detail["receiver_label"] == "مشاور"
    assert detail["direction"] == "O"
    assert detail["direction_label"] == "صادره"

    list_response = client.get("/api/v1/transmittal/", headers=headers)
    assert list_response.status_code == 200, list_response.text
    row = next(item for item in list_response.json() if item.get("transmittal_no") == transmittal_no)
    assert row["sender_label"] == org_label
    assert row["receiver_label"] == "مشاور"
    assert row["direction"] == "O"
    assert row["direction_label"] == "صادره"


def test_lookup_dictionary_endpoint_available():
    response = client.get("/api/v1/lookup/dictionary", headers=_auth_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True
    assert isinstance(body.get("data"), dict)


def test_ui_partial_endpoint_returns_whitelisted_view_html():
    response = client.get("/ui/partial/settings")
    assert response.status_code == 200, response.text
    assert "view-settings" in response.text


def test_ui_partial_endpoint_rejects_unknown_view_name():
    response = client.get("/ui/partial/not-a-real-view")
    assert response.status_code == 404, response.text


def test_index_page_contains_lazy_placeholders_for_heavy_views():
    response = client.get("/")
    assert response.status_code == 200, response.text
    html = response.text
    assert 'data-lazy-view="edms"' in html
    assert 'data-lazy-view="settings"' in html
    assert 'data-lazy-view="reports"' in html


def test_users_response_contains_created_at_field():
    headers = _auth_headers()
    response = client.get("/api/v1/users/", headers=headers)
    assert response.status_code == 200, response.text
    users = response.json()
    assert isinstance(users, list)
    if users:
        assert "created_at" in users[0]


def test_users_paged_response_contains_pagination_meta():
    headers = _auth_headers()
    response = client.get("/api/v1/users/paged?page=1&page_size=5&q=admin", headers=headers)
    assert response.status_code == 200, response.text

    body = response.json()
    assert body.get("ok") is True
    assert isinstance(body.get("items"), list)
    pagination = body.get("pagination", {})
    for key in ("total", "page", "page_size", "total_pages", "count", "has_prev", "has_next"):
        assert key in pagination
    assert pagination.get("page") == 1
    assert pagination.get("page_size") == 5
    assert pagination.get("count") == len(body.get("items", []))


def test_users_paged_scope_summary_keeps_effective_scope_fields():
    headers = _auth_headers()
    project_code, discipline_code = ensure_project_discipline(client, headers)
    scoped_user = create_scoped_user_and_login(
        client,
        headers,
        org_type="contractor",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix=f"user_scope_{uuid.uuid4().hex[:6]}",
        role="user",
        organization_role="user",
    )

    response = client.get(
        f"/api/v1/users/paged?page=1&page_size=10&q={scoped_user['email']}",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    items = body.get("items") or []
    assert items, body
    item = next((row for row in items if row.get("email") == scoped_user["email"]), None)
    assert item, items

    summary = item.get("scope_summary") or {}
    assert summary.get("status") == "restricted"
    assert summary.get("source") in {"user", "intersection", "role", "empty_intersection"}
    assert summary.get("user_projects_count", 0) >= 1
    assert summary.get("effective_projects_count", 0) >= 1
    assert summary.get("user_disciplines_count", 0) >= 1
    assert summary.get("effective_disciplines_count", 0) >= 1


def test_archive_list_includes_mdr_documents_without_uploaded_files():
    headers = _auth_headers()
    project_code, discipline_code = ensure_project_discipline(client, headers)
    doc_number = f"{project_code}-E{uuid.uuid4().hex[:6].upper()}-TGEN"
    document_id = 0

    with SessionLocal() as db:
        document = MdrDocument(
            doc_number=doc_number,
            doc_title_e="MDR Only Test Document",
            doc_title_p="سند فقط MDR",
            subject="MDR Only Test Document",
            project_code=project_code,
            discipline_code=discipline_code,
            mdr_code="E",
            package_code=None,
            block="T",
            level_code=None,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        document_id = int(document.id or 0)

    try:
        response = client.get(
            f"/api/v1/archive/list?search={doc_number}&limit=50",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("ok") is True
        summary = body.get("summary") or {}
        assert summary.get("total_documents", 0) >= 1
        assert summary.get("mdr_only", 0) >= 1
        rows = body.get("data") or []
        row = next((item for item in rows if int(item.get("document_id") or 0) == document_id), None)
        assert row is not None, rows
        assert row.get("is_mdr_only") is True
        assert row.get("has_uploaded_file") is False
        assert row.get("pdf_file_id") is None
        assert row.get("native_file_id") is None
        assert "MDR" in str(row.get("row_message") or "")

        only_mdr_response = client.get(
            f"/api/v1/archive/list?search={doc_number}&file_presence=mdr_only&limit=50",
            headers=headers,
        )
        assert only_mdr_response.status_code == 200, only_mdr_response.text
        only_mdr_summary = only_mdr_response.json().get("summary") or {}
        assert only_mdr_summary.get("with_file") == 0
        assert only_mdr_summary.get("mdr_only", 0) >= 1
        only_mdr_rows = only_mdr_response.json().get("data") or []
        assert any(int(item.get("document_id") or 0) == document_id for item in only_mdr_rows)

        with_file_response = client.get(
            f"/api/v1/archive/list?search={doc_number}&file_presence=with_file&limit=50",
            headers=headers,
        )
        assert with_file_response.status_code == 200, with_file_response.text
        with_file_summary = with_file_response.json().get("summary") or {}
        assert with_file_summary.get("mdr_only") == 0
        with_file_rows = with_file_response.json().get("data") or []
        assert all(int(item.get("document_id") or 0) != document_id for item in with_file_rows)
    finally:
        if document_id > 0:
            with SessionLocal() as db:
                document = db.query(MdrDocument).filter(MdrDocument.id == document_id).first()
                if document is not None:
                    db.delete(document)
                    db.commit()


def test_bulk_register_respects_project_and_mdr_from_manual_format():
    headers = _auth_headers()
    project_code = f"T{uuid.uuid4().hex[:5].upper()}"
    subject = f"manual-{uuid.uuid4().hex[:6]}"
    line = "\t".join(
        [
            project_code,  # project
            "E",           # mdr
            "X",           # phase
            "GN",          # disc
            "00",          # pkg
            "G",           # block
            "GEN",         # level
            subject,       # subject
            "",            # title_p
            "",            # title_e
            "",            # code (let backend generate)
        ]
    )

    response = client.post(
        "/api/v1/mdr/bulk-register",
        headers={**headers, "Content-Type": "application/json"},
        json={"text_data": line},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True

    details = body.get("stats", {}).get("details", [])
    assert details, body
    assert any(str(d.get("doc_number", "")).startswith(f"{project_code}-E") for d in details), body


def test_system_init_requires_admin_auth():
    response = client.get(f"{API_PREFIX}/init")
    assert response.status_code in (401, 403)


def test_system_init_disabled_in_production_for_admin(monkeypatch):
    headers = _auth_headers()
    monkeypatch.setattr(settings, "APP_ENV", "production")
    response = client.get(f"{API_PREFIX}/init", headers=headers)
    assert response.status_code == 403, response.text


def test_read_only_mode_blocks_write_routes_but_allows_login(monkeypatch):
    headers = _auth_headers()
    monkeypatch.setattr(settings, "READ_ONLY_MODE", True)

    write_response = client.post(
        f"{API_PREFIX}/transmittal/create",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "project_code": "T202",
            "sender": "O",
            "receiver": "C",
            "subject": "read-only-test",
            "notes": "",
            "documents": [],
        },
    )
    assert write_response.status_code == 503, write_response.text

    email, password = get_test_admin_credentials()
    login_response = client.post(
        f"{API_PREFIX}/auth/login",
        data={"username": email, "password": password},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    # Allowed by read-only middleware; auth itself may return 200/401 depending on credentials.
    assert login_response.status_code != 503, login_response.text


def test_settings_overview_masks_database_url(monkeypatch):
    headers = _auth_headers()
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+psycopg://user:super-secret@db.example:5432/mdr")
    response = client.get(f"{API_PREFIX}/settings/overview", headers=headers)
    if response.status_code == 404 and API_PREFIX != "/api/v1":
        response = client.get("/api/v1/settings/overview", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("ok") is True
    db_payload = payload.get("db", {})
    assert isinstance(db_payload, dict)
    url_value = str(db_payload.get("url") or "")
    assert "super-secret" not in url_value
    assert "***" in url_value


def test_transmittal_lifecycle_edit_issue_void_rules():
    headers = _auth_headers()
    payload = {
        "project_code": "T202",
        "sender": "O",
        "receiver": "C",
        "subject": f"life-{uuid.uuid4().hex[:6]}",
        "notes": "",
        "documents": [],
    }

    create_res = client.post(
        "/api/v1/transmittal/create",
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
    )
    assert create_res.status_code == 200, create_res.text
    transmittal_no = create_res.json()["transmittal_no"]
    assert create_res.json().get("status") == "draft"

    edit_payload = {**payload, "sender": "I"}
    edit_res = client.put(
        f"/api/v1/transmittal/item/{transmittal_no}",
        headers={**headers, "Content-Type": "application/json"},
        json=edit_payload,
    )
    assert edit_res.status_code == 200, edit_res.text

    issue_res = client.post(f"/api/v1/transmittal/item/{transmittal_no}/issue", headers=headers)
    assert issue_res.status_code == 200, issue_res.text
    assert issue_res.json().get("status") == "issued"

    edit_after_issue = client.put(
        f"/api/v1/transmittal/item/{transmittal_no}",
        headers={**headers, "Content-Type": "application/json"},
        json=edit_payload,
    )
    assert edit_after_issue.status_code == 409, edit_after_issue.text

    void_without_reason = client.post(f"/api/v1/transmittal/item/{transmittal_no}/void", headers=headers, json={})
    assert void_without_reason.status_code == 422, void_without_reason.text

    reason = f"Wrong issue target {uuid.uuid4().hex[:5]}"
    void_after_issue = client.post(
        f"/api/v1/transmittal/item/{transmittal_no}/void",
        headers={**headers, "Content-Type": "application/json"},
        json={"reason": reason},
    )
    assert void_after_issue.status_code == 200, void_after_issue.text
    void_body = void_after_issue.json()
    assert void_body.get("status") == "void"
    assert void_body.get("void_reason") == reason
    assert void_body.get("voided_by")
    assert void_body.get("voided_at")

    list_after_void = client.get("/api/v1/transmittal/", headers=headers)
    assert list_after_void.status_code == 200, list_after_void.text
    row = next((item for item in list_after_void.json() if item.get("transmittal_no") == transmittal_no), None)
    assert row is not None
    assert row.get("status") == "void"
    assert row.get("void_reason") == reason
