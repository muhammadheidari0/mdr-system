from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import io
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import (
    ArchiveFile,
    CommItem,
    DocumentActivity,
    DocumentRevision,
    PermitQcPermit,
    SiteLog,
    UserDisciplineScope,
    UserProjectScope,
)
from app.db.session import SessionLocal
from app.main import app
from app.services.storage_policy import get_storage_integrations, set_storage_integrations
from tests.auth_helpers import get_auth_headers
from tests.site_logs_helpers import ensure_org


client = TestClient(app)

PROJECT_CODE = "TSEED"
DISCIPLINE_CODE = "GN"


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _ensure_reclassify_lookups(headers: dict[str, str]) -> None:
    requests = [
        (
            "/api/v1/settings/projects/upsert",
            {"code": PROJECT_CODE, "project_name": PROJECT_CODE, "name_e": PROJECT_CODE, "is_active": True},
        ),
        (
            "/api/v1/settings/disciplines/upsert",
            {"code": DISCIPLINE_CODE, "name_e": "General", "name_p": "General"},
        ),
        (
            "/api/v1/settings/phases/upsert",
            {"ph_code": "X", "name_e": "Phase X", "name_p": "Phase X"},
        ),
        (
            "/api/v1/settings/mdr-categories/upsert",
            {"code": "E", "name_e": "Engineering", "name_p": "Engineering", "folder_name": "Engineering", "is_active": True},
        ),
        (
            "/api/v1/settings/levels/upsert",
            {"code": "GEN", "name_e": "General", "name_p": "General", "sort_order": 10},
        ),
        (
            "/api/v1/settings/blocks/upsert",
            {"project_code": PROJECT_CODE, "code": "T", "name_e": "Tower", "name_p": "Tower", "is_active": True},
        ),
        (
            "/api/v1/settings/packages/upsert",
            {"discipline_code": DISCIPLINE_CODE, "package_code": "00", "name_e": "Pkg 00", "name_p": "Pkg 00"},
        ),
    ]
    for url, payload in requests:
        response = client.post(url, json=payload, headers=headers)
        assert response.status_code == 200, response.text


def _register_document(
    headers: dict[str, str],
    *,
    project_code: str = PROJECT_CODE,
    discipline_code: str = DISCIPLINE_CODE,
    subject_prefix: str = "DocDetail",
) -> tuple[int, str]:
    doc_number = f"{project_code}-EGN{uuid4().hex[:4].upper()}01-TGEN"
    subject = f"{subject_prefix}-{uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": doc_number,
            "project_code": project_code,
            "mdr_code": "E",
            "phase": "X",
            "discipline": discipline_code,
            "package": "00",
            "block": "T",
            "level": "GEN",
            "subject_e": subject,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("ok") is True
    document_id = int(payload.get("document_id") or 0)
    assert document_id > 0
    return document_id, doc_number


def test_archive_registration_uses_only_active_mdr_categories() -> None:
    headers = _admin_headers()
    _ensure_reclassify_lookups(headers)
    inactive_code = "ZZ"

    inactive_response = client.post(
        "/api/v1/settings/mdr-categories/upsert",
        json={
            "code": inactive_code,
            "name_e": "Inactive MDR",
            "name_p": "Inactive MDR",
            "folder_name": "Inactive MDR",
            "sort_order": 999,
            "is_active": False,
        },
        headers=headers,
    )
    assert inactive_response.status_code == 200, inactive_response.text

    form_response = client.get("/api/v1/archive/form-data", headers=headers)
    assert form_response.status_code == 200, form_response.text
    mdr_codes = {
        str(item.get("code") or "").strip().upper()
        for item in form_response.json().get("mdr_categories", [])
    }
    assert inactive_code not in mdr_codes
    assert "E" in mdr_codes

    serial_response = client.get(
        "/api/v1/archive/next-serial",
        params={
            "project_code": PROJECT_CODE,
            "mdr_code": inactive_code,
            "phase": "X",
            "discipline": DISCIPLINE_CODE,
            "pkg": "00",
            "block": "T",
            "level": "GEN",
            "subject_e": f"Inactive MDR {uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert serial_response.status_code == 422, serial_response.text

    register_response = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": f"{PROJECT_CODE}-{inactive_code}{DISCIPLINE_CODE}{uuid4().hex[:4].upper()}01-TGEN",
            "project_code": PROJECT_CODE,
            "mdr_code": inactive_code,
            "phase": "X",
            "discipline": DISCIPLINE_CODE,
            "package": "00",
            "block": "T",
            "level": "GEN",
            "subject_e": f"Inactive MDR {uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert register_response.status_code == 422, register_response.text
    assert "MDR" in str(register_response.json().get("detail") or "")


def _upload_file(
    headers: dict[str, str],
    *,
    document_id: int,
    filename: str,
    content: bytes,
    mime_type: str,
    revision: str = "00",
    status: str = "IFA",
    file_kind: str = "pdf",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/archive/upload",
        data={
            "document_id": str(document_id),
            "revision": revision,
            "status": status,
            "file_kind": file_kind,
        },
        files={"file": (filename, io.BytesIO(content), mime_type)},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("ok") is True
    return payload


def _create_scoped_user(
    admin_headers: dict[str, str],
    *,
    role: str,
    org_type: str,
    email_prefix: str,
    project_code: str = PROJECT_CODE,
    discipline_code: str = DISCIPLINE_CODE,
) -> dict[str, Any]:
    organization_id = ensure_org(
        client,
        admin_headers,
        org_type=org_type,
        code_prefix=email_prefix.upper(),
    )
    assert organization_id > 0

    email = f"{email_prefix}_{uuid4().hex[:8]}@mdr.local"
    password = f"Pwd!{uuid4().hex[:10]}"
    create_response = client.post(
        "/api/v1/users/",
        json={
            "email": email,
            "password": password,
            "full_name": f"{role.title()} {email_prefix}",
            "role": role,
            "organization_id": organization_id,
            "organization_role": role,
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert create_response.status_code == 200, create_response.text
    user_id = int(create_response.json().get("id") or 0)
    assert user_id > 0

    with SessionLocal() as db:
        has_project_scope = (
            db.query(UserProjectScope.id)
            .filter(
                UserProjectScope.user_id == user_id,
                UserProjectScope.project_code == project_code,
            )
            .first()
        )
        if not has_project_scope:
            db.add(UserProjectScope(user_id=user_id, project_code=project_code))

        has_discipline_scope = (
            db.query(UserDisciplineScope.id)
            .filter(
                UserDisciplineScope.user_id == user_id,
                UserDisciplineScope.discipline_code == discipline_code,
            )
            .first()
        )
        if not has_discipline_scope:
            db.add(
                UserDisciplineScope(
                    user_id=user_id,
                    discipline_code=discipline_code,
                )
            )
        db.commit()

    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert login_response.status_code == 200, login_response.text
    token = str(login_response.json().get("access_token") or "").strip()
    assert token

    return {
        "user_id": user_id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def _get_activity_actions(document_id: int, headers: dict[str, str]) -> set[str]:
    response = client.get(
        f"/api/v1/archive/documents/{document_id}/activity",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    return {
        str(item.get("action"))
        for item in (payload.get("data") or [])
        if str(item.get("action") or "").strip()
    }


def _get_permission_matrix(admin_headers: dict[str, str], category: str) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/settings/permissions/matrix?category={category}",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("ok") is True
    return payload


def _save_permission_matrix(
    admin_headers: dict[str, str],
    category: str,
    matrix: dict[str, dict[str, bool]],
) -> None:
    response = client.post(
        f"/api/v1/settings/permissions/matrix?category={category}",
        json={"matrix": matrix},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json().get("ok") is True


def _get_permission_scope(admin_headers: dict[str, str], category: str) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/settings/permissions/scope?category={category}",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("ok") is True
    return payload


def _save_permission_scope(
    admin_headers: dict[str, str],
    category: str,
    scope: dict[str, dict[str, list[str]]],
) -> None:
    response = client.post(
        f"/api/v1/settings/permissions/scope?category={category}",
        json={"scope": scope},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json().get("ok") is True


def _flatten_comment_ids(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {}

    def _walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            node_id = int(node.get("id") or 0)
            if node_id:
                output[node_id] = node
            children = node.get("children") or []
            if children:
                _walk(children)

    _walk(items)
    return output


def test_document_detail_update_delete_and_soft_delete_filters() -> None:
    admin = _admin_headers()
    document_id, doc_number = _register_document(admin, subject_prefix="DetailOps")
    upload_payload = _upload_file(
        admin,
        document_id=document_id,
        filename="detail.pdf",
        content=b"%PDF-1.4\n%document-detail\n",
        mime_type="application/pdf",
    )
    file_id = int(upload_payload.get("file_id") or 0)
    assert file_id > 0

    detail_response = client.get(f"/api/v1/archive/documents/{document_id}", headers=admin)
    assert detail_response.status_code == 200, detail_response.text
    detail_payload = detail_response.json()
    assert detail_payload.get("ok") is True
    assert detail_payload.get("document", {}).get("doc_number") == doc_number
    assert detail_payload.get("is_deleted") is False
    assert detail_payload.get("capabilities", {}).get("can_edit") is True

    locked_update_response = client.put(
        f"/api/v1/archive/documents/{document_id}",
        json={
            "doc_title_e": "Updated Title API",
            "phase_code": "E",
        },
        headers=admin,
    )
    assert locked_update_response.status_code == 422, locked_update_response.text

    update_response = client.put(
        f"/api/v1/archive/documents/{document_id}",
        json={
            "subject": "Updated Subject API",
            "notes": "Updated Notes API",
        },
        headers=admin,
    )
    assert update_response.status_code == 200, update_response.text
    updated_doc = update_response.json().get("document") or {}
    assert updated_doc.get("subject") == "Updated Subject API"
    assert "Updated Subject API" in str(updated_doc.get("doc_title_e") or "")
    assert "Updated Subject API" in str(updated_doc.get("doc_title_p") or "")
    assert updated_doc.get("notes") == "Updated Notes API"
    assert updated_doc.get("updated_at")

    delete_response = client.delete(f"/api/v1/archive/documents/{document_id}", headers=admin)
    assert delete_response.status_code == 200, delete_response.text
    delete_payload = delete_response.json()
    assert delete_payload.get("ok") is True
    assert int(delete_payload.get("document_id") or 0) == document_id
    assert delete_payload.get("deleted_at")

    deleted_detail = client.get(f"/api/v1/archive/documents/{document_id}", headers=admin)
    assert deleted_detail.status_code == 200, deleted_detail.text
    deleted_payload = deleted_detail.json()
    assert deleted_payload.get("is_deleted") is True
    capabilities = deleted_payload.get("capabilities") or {}
    assert capabilities.get("can_edit") is False
    assert capabilities.get("can_delete") is False
    assert capabilities.get("can_comment") is False
    assert capabilities.get("can_manage_relations") is False
    assert capabilities.get("can_manage_tags") is False

    list_response = client.get("/api/v1/archive/list", params={"search": doc_number}, headers=admin)
    assert list_response.status_code == 200, list_response.text
    list_rows = list_response.json().get("data") or []
    assert all(int(row.get("document_id") or 0) != document_id for row in list_rows)

    suggestions_response = client.get(
        "/api/v1/archive/doc-suggestions",
        params={"q": doc_number, "project_code": PROJECT_CODE},
        headers=admin,
    )
    assert suggestions_response.status_code == 200, suggestions_response.text
    suggestions = suggestions_response.json().get("items") or []
    assert all(int(row.get("id") or 0) != document_id for row in suggestions)

    eligible_response = client.get(
        "/api/v1/transmittal/eligible-docs",
        params={"project_code": PROJECT_CODE, "q": doc_number},
        headers=admin,
    )
    assert eligible_response.status_code == 200, eligible_response.text
    eligible_rows = eligible_response.json()
    assert isinstance(eligible_rows, list)
    assert all(str(row.get("doc_number") or "") != doc_number for row in eligible_rows)

    download_deleted_file = client.get(f"/api/v1/archive/download/{file_id}", headers=admin)
    assert download_deleted_file.status_code == 404, download_deleted_file.text
    integrity_deleted_file = client.get(f"/api/v1/archive/files/{file_id}/integrity", headers=admin)
    assert integrity_deleted_file.status_code == 404, integrity_deleted_file.text

    actions = _get_activity_actions(document_id, admin)
    assert "metadata_updated" in actions
    assert "deleted" in actions


def test_document_preview_endpoint_and_unsupported_preview_meta() -> None:
    admin = _admin_headers()

    preview_doc_id, _ = _register_document(admin, subject_prefix="PreviewDoc")
    _upload_file(
        admin,
        document_id=preview_doc_id,
        filename="preview.pdf",
        content=b"%PDF-1.4\n%preview\n",
        mime_type="application/pdf",
    )
    preview_response = client.get(f"/api/v1/archive/documents/{preview_doc_id}/preview", headers=admin)
    assert preview_response.status_code == 200, preview_response.text
    disposition = str(preview_response.headers.get("content-disposition") or "").lower()
    assert "inline" in disposition
    content_type = str(preview_response.headers.get("content-type") or "").lower()
    assert "application/pdf" in content_type

    unsupported_doc_id, _ = _register_document(admin, subject_prefix="NoPreviewDoc")
    _upload_file(
        admin,
        document_id=unsupported_doc_id,
        filename="notes.txt",
        content=b"plain text file",
        mime_type="text/plain",
        file_kind="native",
    )

    unsupported_detail = client.get(f"/api/v1/archive/documents/{unsupported_doc_id}", headers=admin)
    assert unsupported_detail.status_code == 200, unsupported_detail.text
    preview_meta = unsupported_detail.json().get("preview_meta") or {}
    assert preview_meta.get("has_preview") is False
    assert preview_meta.get("supported") is False

    unsupported_preview = client.get(f"/api/v1/archive/documents/{unsupported_doc_id}/preview", headers=admin)
    assert unsupported_preview.status_code == 404, unsupported_preview.text


def test_document_subject_duplicate_guard_and_reclassify_flow() -> None:
    admin = _admin_headers()
    _ensure_reclassify_lookups(admin)
    source_id, source_number = _register_document(admin, subject_prefix="ReclassSource")
    duplicate_id, _ = _register_document(admin, subject_prefix="ReclassDuplicate")
    _upload_file(
        admin,
        document_id=source_id,
        filename="reclass.pdf",
        content=b"%PDF-1.4\n%reclass-before\n",
        mime_type="application/pdf",
    )

    source_detail = client.get(f"/api/v1/archive/documents/{source_id}", headers=admin)
    assert source_detail.status_code == 200, source_detail.text
    source_subject = str(source_detail.json().get("document", {}).get("subject") or "").strip()
    assert source_subject

    duplicate_update = client.put(
        f"/api/v1/archive/documents/{duplicate_id}",
        json={"subject": source_subject},
        headers=admin,
    )
    assert duplicate_update.status_code == 409, duplicate_update.text

    payload = {
        "project_code": PROJECT_CODE,
        "mdr_code": "E",
        "phase_code": "X",
        "discipline_code": DISCIPLINE_CODE,
        "package_code": "00",
        "block": "T",
        "level_code": "GEN",
    }
    preview_response = client.post(
        f"/api/v1/archive/documents/{source_id}/reclassify/preview",
        json=payload,
        headers=admin,
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json().get("preview") or {}
    new_number = str(preview.get("doc_number") or "").strip()
    assert new_number
    assert new_number != source_number
    assert source_subject in str(preview.get("doc_title_e") or "")

    reclassify_response = client.post(
        f"/api/v1/archive/documents/{source_id}/reclassify",
        json=payload,
        headers=admin,
    )
    assert reclassify_response.status_code == 200, reclassify_response.text
    updated = reclassify_response.json().get("document") or {}
    assert updated.get("doc_number") == new_number
    assert updated.get("phase_code") == "X"
    assert updated.get("package_code") == "00"

    detail_after = client.get(f"/api/v1/archive/documents/{source_id}", headers=admin)
    assert detail_after.status_code == 200, detail_after.text
    latest_file = detail_after.json().get("latest_files", {}).get("latest") or {}
    file_id = int(latest_file.get("id") or 0)
    assert file_id > 0
    assert str(latest_file.get("name") or "").startswith(new_number)
    download_after = client.get(f"/api/v1/archive/download/{file_id}", headers=admin)
    assert download_after.status_code == 200, download_after.text

    with SessionLocal() as db:
        actions = {
            str(row.action or "")
            for row in db.query(DocumentActivity).filter(DocumentActivity.document_id == source_id).all()
        }
    assert "document_reclassified" in actions

    invalid_package = dict(payload)
    invalid_package["discipline_code"] = "NO_SUCH_DISC"
    invalid_response = client.post(
        f"/api/v1/archive/documents/{source_id}/reclassify/preview",
        json=invalid_package,
        headers=admin,
    )
    assert invalid_response.status_code == 422, invalid_response.text


def test_replace_archive_file_keeps_revision_and_deletes_old_record() -> None:
    admin = _admin_headers()
    document_id, _ = _register_document(admin, subject_prefix="ReplaceFile")
    upload_payload = _upload_file(
        admin,
        document_id=document_id,
        filename="replace-before.pdf",
        content=b"%PDF-1.4\n%old-file\n",
        mime_type="application/pdf",
    )
    old_file_id = int(upload_payload.get("file_id") or 0)
    assert old_file_id > 0

    with SessionLocal() as db:
        old_row = db.query(ArchiveFile).filter(ArchiveFile.id == old_file_id).first()
        assert old_row is not None
        old_revision_id = int(old_row.revision_id or 0)

    replace_response = client.post(
        f"/api/v1/archive/files/{old_file_id}/replace",
        data={"status": "IFA"},
        files={"file": ("replace-after.pdf", io.BytesIO(b"%PDF-1.4\n%new-file\n"), "application/pdf")},
        headers=admin,
    )
    assert replace_response.status_code == 200, replace_response.text
    new_file_id = int((replace_response.json().get("file") or {}).get("id") or 0)
    assert new_file_id > 0
    assert new_file_id != old_file_id

    old_download = client.get(f"/api/v1/archive/download/{old_file_id}", headers=admin)
    assert old_download.status_code == 404, old_download.text
    new_download = client.get(f"/api/v1/archive/download/{new_file_id}", headers=admin)
    assert new_download.status_code == 200, new_download.text
    assert b"%new-file" in new_download.content

    with SessionLocal() as db:
        old_row = db.query(ArchiveFile).filter(ArchiveFile.id == old_file_id).first()
        new_row = db.query(ArchiveFile).filter(ArchiveFile.id == new_file_id).first()
        assert old_row is not None and old_row.deleted_at is not None
        assert new_row is not None and int(new_row.revision_id or 0) == old_revision_id


def test_add_complementary_file_to_existing_revision_without_new_revision() -> None:
    admin = _admin_headers()
    document_id, _ = _register_document(admin, subject_prefix="ComplementaryRevisionFile")
    native_payload = _upload_file(
        admin,
        document_id=document_id,
        filename="complementary-native.dwg",
        content=b"AC1018DWG\nnative\n",
        mime_type="application/x-dwg",
        file_kind="native",
    )
    native_file_id = int(native_payload.get("file_id") or 0)
    assert native_file_id > 0

    detail_before = client.get(f"/api/v1/archive/documents/{document_id}", headers=admin)
    assert detail_before.status_code == 200, detail_before.text
    revisions_before = detail_before.json().get("revisions") or []
    assert len(revisions_before) == 1
    revision_id = int(revisions_before[0].get("revision_id") or 0)
    assert revision_id > 0
    assert {str(file.get("file_kind") or "") for file in revisions_before[0].get("files") or []} == {"native"}

    add_pdf = client.post(
        f"/api/v1/archive/revisions/{revision_id}/files",
        data={"file_kind": "pdf", "status": "IFA"},
        files={"file": ("complementary-output.pdf", io.BytesIO(b"%PDF-1.4\n%output\n"), "application/pdf")},
        headers=admin,
    )
    assert add_pdf.status_code == 200, add_pdf.text
    pdf_file_id = int((add_pdf.json().get("file") or {}).get("id") or 0)
    assert pdf_file_id > 0

    duplicate_pdf = client.post(
        f"/api/v1/archive/revisions/{revision_id}/files",
        data={"file_kind": "pdf", "status": "IFA"},
        files={"file": ("duplicate-output.pdf", io.BytesIO(b"%PDF-1.4\n%duplicate\n"), "application/pdf")},
        headers=admin,
    )
    assert duplicate_pdf.status_code == 409, duplicate_pdf.text

    detail_after = client.get(f"/api/v1/archive/documents/{document_id}", headers=admin)
    assert detail_after.status_code == 200, detail_after.text
    revisions_after = detail_after.json().get("revisions") or []
    assert len(revisions_after) == 1
    files_after = revisions_after[0].get("files") or []
    assert {str(file.get("file_kind") or "") for file in files_after} == {"pdf", "native"}

    with SessionLocal() as db:
        native_row = db.query(ArchiveFile).filter(ArchiveFile.id == native_file_id).first()
        pdf_row = db.query(ArchiveFile).filter(ArchiveFile.id == pdf_file_id).first()
        assert native_row is not None and int(native_row.companion_file_id or 0) == pdf_file_id
        assert pdf_row is not None and int(pdf_row.companion_file_id or 0) == native_file_id
        assert int(native_row.revision_id or 0) == revision_id
        assert int(pdf_row.revision_id or 0) == revision_id

    pdf_download = client.get(f"/api/v1/archive/download/{pdf_file_id}", headers=admin)
    assert pdf_download.status_code == 200, pdf_download.text
    assert b"%output" in pdf_download.content


class _FakePublicShareAdapter:
    def __init__(self, *, exists: bool = True) -> None:
        self.exists = exists
        self.exists_paths: list[str] = []
        self.create_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []

    def file_exists(self, remote_relative_path: str) -> bool:
        self.exists_paths.append(remote_relative_path)
        return self.exists

    def create_public_share(
        self,
        *,
        remote_relative_path: str,
        password: str | None = None,
        expire_date: str | None = None,
        permissions: int = 1,
    ) -> dict[str, Any]:
        self.create_calls.append(
            {
                "remote_relative_path": remote_relative_path,
                "password": password,
                "expire_date": expire_date,
                "permissions": permissions,
            }
        )
        idx = len(self.create_calls)
        return {
            "provider_share_id": f"share-{idx}",
            "url": f"https://nextcloud.example.com/s/token-{idx}",
            "token": f"token-{idx}",
            "path": remote_relative_path,
        }

    def delete_share(self, provider_share_id: str) -> bool:
        self.delete_calls.append(str(provider_share_id))
        return True


def _make_archive_file_for_public_share(
    headers: dict[str, str],
    *,
    subject_prefix: str,
) -> tuple[int, int]:
    document_id, _doc_number = _register_document(headers, subject_prefix=subject_prefix)
    upload_payload = _upload_file(
        headers,
        document_id=document_id,
        filename=f"{subject_prefix.lower()}.pdf",
        content=b"%PDF-1.4\n%public-share\n",
        mime_type="application/pdf",
    )
    file_id = int(upload_payload.get("file_id") or 0)
    assert file_id > 0
    return document_id, file_id


def test_archive_public_share_primary_nextcloud_create_get_and_revoke(monkeypatch) -> None:
    from app.services import archive_service as archive_service_module

    admin = _admin_headers()
    document_id, file_id = _make_archive_file_for_public_share(admin, subject_prefix="SharePrimary")
    with SessionLocal() as db:
        row = db.query(ArchiveFile).filter(ArchiveFile.id == file_id).first()
        assert row is not None
        row.stored_path = "webdav://archive/TSEED/share-primary.pdf"
        row.storage_backend = "nextcloud"
        row.mirror_provider = None
        row.mirror_status = None
        row.mirror_remote_id = None
        db.commit()

    adapter = _FakePublicShareAdapter()
    monkeypatch.setattr(archive_service_module, "_nextcloud_adapter", lambda _db: adapter)
    expire_date = (date.today() + timedelta(days=60)).isoformat()
    create_response = client.post(
        f"/api/v1/archive/files/{file_id}/public-share",
        json={"password": "Manual-Secret-1", "expire_date": expire_date},
        headers=admin,
    )
    assert create_response.status_code == 200, create_response.text
    created = create_response.json()
    assert created["public_share_supported"] is True
    assert created["public_share_source"] == "primary_nextcloud"
    assert created["public_share_status"] == "available"
    assert created["public_share"]["url"] == "https://nextcloud.example.com/s/token-1"
    assert created["public_share"]["password"] == "Manual-Secret-1"
    assert adapter.exists_paths == ["/archive/TSEED/share-primary.pdf"]
    assert adapter.create_calls[0]["remote_relative_path"] == "/archive/TSEED/share-primary.pdf"
    assert adapter.create_calls[0]["expire_date"] == expire_date

    get_response = client.get(f"/api/v1/archive/files/{file_id}/public-share", headers=admin)
    assert get_response.status_code == 200, get_response.text
    listed_share = get_response.json()["public_share"]
    assert listed_share["url"] == "https://nextcloud.example.com/s/token-1"
    assert "password" not in listed_share

    detail_response = client.get(f"/api/v1/archive/documents/{document_id}", headers=admin)
    assert detail_response.status_code == 200, detail_response.text
    files = [
        file
        for revision in detail_response.json().get("revisions") or []
        for file in revision.get("files") or []
        if int(file.get("id") or 0) == file_id
    ]
    assert files and files[0]["public_share_supported"] is True
    assert files[0]["public_share"]["url"] == "https://nextcloud.example.com/s/token-1"
    assert "password" not in files[0]["public_share"]

    revoke_response = client.delete(f"/api/v1/archive/files/{file_id}/public-share", headers=admin)
    assert revoke_response.status_code == 200, revoke_response.text
    assert adapter.delete_calls == ["share-1"]
    assert revoke_response.json()["public_share"] is None


def test_archive_public_share_mirror_nextcloud_uses_mirror_remote_id(monkeypatch) -> None:
    from app.services import archive_service as archive_service_module

    admin = _admin_headers()
    _document_id, file_id = _make_archive_file_for_public_share(admin, subject_prefix="ShareMirror")
    with SessionLocal() as db:
        before_integrations = get_storage_integrations(db)
        next_integrations = deepcopy(before_integrations)
        nextcloud_cfg = dict(next_integrations.get("nextcloud") or {})
        nextcloud_cfg["public_share_password"] = "Configured-Share-Password"
        next_integrations["nextcloud"] = nextcloud_cfg
        set_storage_integrations(db, next_integrations)
        row = db.query(ArchiveFile).filter(ArchiveFile.id == file_id).first()
        assert row is not None
        row.storage_backend = "local"
        row.mirror_provider = "nextcloud"
        row.mirror_status = "mirrored"
        row.mirror_remote_id = "mirror/archive/share-mirror.pdf"
        db.commit()

    adapter = _FakePublicShareAdapter()
    monkeypatch.setattr(archive_service_module, "_nextcloud_adapter", lambda _db: adapter)
    try:
        response = client.post(
            f"/api/v1/archive/files/{file_id}/public-share",
            json={},
            headers=admin,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["public_share_supported"] is True
        assert payload["public_share_source"] == "mirror_nextcloud"
        assert adapter.create_calls[0]["remote_relative_path"] == "/mirror/archive/share-mirror.pdf"
        assert adapter.create_calls[0]["password"] == "Configured-Share-Password"
        assert payload["public_share"]["password"] == "Configured-Share-Password"
    finally:
        with SessionLocal() as db:
            set_storage_integrations(db, before_integrations)
            db.commit()


def test_archive_public_share_can_create_without_password_when_setting_disabled(monkeypatch) -> None:
    from app.services import archive_service as archive_service_module

    admin = _admin_headers()
    _document_id, file_id = _make_archive_file_for_public_share(admin, subject_prefix="ShareNoPassword")
    with SessionLocal() as db:
        before_integrations = get_storage_integrations(db)
        next_integrations = deepcopy(before_integrations)
        nextcloud_cfg = dict(next_integrations.get("nextcloud") or {})
        nextcloud_cfg["public_share_password"] = "Ignored-When-Optional"
        nextcloud_cfg["public_share_password_required"] = False
        next_integrations["nextcloud"] = nextcloud_cfg
        set_storage_integrations(db, next_integrations)
        row = db.query(ArchiveFile).filter(ArchiveFile.id == file_id).first()
        assert row is not None
        row.stored_path = "webdav://archive/TSEED/share-no-password.pdf"
        row.storage_backend = "nextcloud"
        db.commit()

    adapter = _FakePublicShareAdapter()
    monkeypatch.setattr(archive_service_module, "_nextcloud_adapter", lambda _db: adapter)
    try:
        response = client.post(f"/api/v1/archive/files/{file_id}/public-share", json={}, headers=admin)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert adapter.create_calls[0]["remote_relative_path"] == "/archive/TSEED/share-no-password.pdf"
        assert adapter.create_calls[0]["password"] is None
        assert payload["public_share"]["password_set"] is False
        assert "password" not in payload["public_share"]
    finally:
        with SessionLocal() as db:
            set_storage_integrations(db, before_integrations)
            db.commit()


def test_archive_public_share_blocks_local_and_unready_mirror(monkeypatch) -> None:
    from app.services import archive_service as archive_service_module

    admin = _admin_headers()
    _document_id, local_file_id = _make_archive_file_for_public_share(admin, subject_prefix="ShareLocal")
    _document_id, pending_file_id = _make_archive_file_for_public_share(admin, subject_prefix="SharePending")
    _document_id, missing_file_id = _make_archive_file_for_public_share(admin, subject_prefix="ShareMissing")
    with SessionLocal() as db:
        pending = db.query(ArchiveFile).filter(ArchiveFile.id == pending_file_id).first()
        missing = db.query(ArchiveFile).filter(ArchiveFile.id == missing_file_id).first()
        assert pending is not None and missing is not None
        pending.mirror_provider = "nextcloud"
        pending.mirror_status = "pending"
        pending.mirror_remote_id = "mirror/archive/pending.pdf"
        missing.mirror_provider = "nextcloud"
        missing.mirror_status = "mirrored"
        missing.mirror_remote_id = None
        db.commit()

    adapter = _FakePublicShareAdapter()
    monkeypatch.setattr(archive_service_module, "_nextcloud_adapter", lambda _db: adapter)

    local_get = client.get(f"/api/v1/archive/files/{local_file_id}/public-share", headers=admin)
    assert local_get.status_code == 200, local_get.text
    assert local_get.json()["public_share_supported"] is False
    assert local_get.json()["public_share_status"] == "not_nextcloud"
    local_post = client.post(f"/api/v1/archive/files/{local_file_id}/public-share", json={}, headers=admin)
    assert local_post.status_code == 409, local_post.text

    pending_get = client.get(f"/api/v1/archive/files/{pending_file_id}/public-share", headers=admin)
    assert pending_get.status_code == 200, pending_get.text
    assert pending_get.json()["public_share_status"] == "mirror_not_ready"
    pending_post = client.post(f"/api/v1/archive/files/{pending_file_id}/public-share", json={}, headers=admin)
    assert pending_post.status_code == 409, pending_post.text

    missing_get = client.get(f"/api/v1/archive/files/{missing_file_id}/public-share", headers=admin)
    assert missing_get.status_code == 200, missing_get.text
    assert missing_get.json()["public_share_status"] == "missing_remote_path"
    missing_post = client.post(f"/api/v1/archive/files/{missing_file_id}/public-share", json={}, headers=admin)
    assert missing_post.status_code == 409, missing_post.text
    assert adapter.create_calls == []


def test_archive_public_share_blocks_missing_nextcloud_file(monkeypatch) -> None:
    from app.services import archive_service as archive_service_module

    admin = _admin_headers()
    _document_id, file_id = _make_archive_file_for_public_share(admin, subject_prefix="ShareMissingRemote")
    with SessionLocal() as db:
        row = db.query(ArchiveFile).filter(ArchiveFile.id == file_id).first()
        assert row is not None
        row.stored_path = "webdav://archive/TSEED/missing-remote.pdf"
        row.storage_backend = "nextcloud"
        db.commit()

    adapter = _FakePublicShareAdapter(exists=False)
    monkeypatch.setattr(archive_service_module, "_nextcloud_adapter", lambda _db: adapter)
    response = client.post(f"/api/v1/archive/files/{file_id}/public-share", json={}, headers=admin)
    assert response.status_code == 409, response.text
    assert "Nextcloud" in str(response.json().get("detail") or "")
    assert adapter.exists_paths == ["/archive/TSEED/missing-remote.pdf"]
    assert adapter.create_calls == []


def test_document_comments_permissions_and_tombstone_behavior() -> None:
    admin = _admin_headers()
    document_id, _ = _register_document(admin, subject_prefix="CommentsDoc")

    matrix_payload = _get_permission_matrix(admin, "consultant")
    original_matrix = deepcopy(matrix_payload.get("matrix") or {})
    available_permissions = {str(item) for item in (matrix_payload.get("permissions") or [])}
    modified_matrix = deepcopy(original_matrix)
    modified_matrix.setdefault("user", {})
    for permission in (
        "documents:comment_create",
        "documents:comment_update",
        "documents:comment_delete",
    ):
        if permission in available_permissions:
            modified_matrix["user"][permission] = True

    scope_payload = _get_permission_scope(admin, "consultant")
    original_scope = deepcopy(scope_payload.get("scope") or {})
    modified_scope = deepcopy(original_scope)
    modified_scope.setdefault("user", {})
    user_projects = {str(code).strip().upper() for code in modified_scope["user"].get("projects", [])}
    user_disciplines = {str(code).strip().upper() for code in modified_scope["user"].get("disciplines", [])}
    user_projects.add(PROJECT_CODE)
    user_disciplines.add(DISCIPLINE_CODE)
    modified_scope["user"]["projects"] = sorted(user_projects)
    modified_scope["user"]["disciplines"] = sorted(user_disciplines)

    _save_permission_matrix(admin, "consultant", modified_matrix)
    _save_permission_scope(admin, "consultant", modified_scope)
    try:
        author = _create_scoped_user(
            admin,
            role="user",
            org_type="consultant",
            email_prefix="doc_comment_author",
        )
        other_user = _create_scoped_user(
            admin,
            role="user",
            org_type="consultant",
            email_prefix="doc_comment_other",
        )
        viewer = _create_scoped_user(
            admin,
            role="viewer",
            org_type="consultant",
            email_prefix="doc_comment_viewer",
        )

        create_root = client.post(
            f"/api/v1/archive/documents/{document_id}/comments",
            json={"body": "Root comment"},
            headers=author["headers"],
        )
        assert create_root.status_code == 200, create_root.text
        root_item = create_root.json().get("item") or {}
        root_id = int(root_item.get("id") or 0)
        assert root_id > 0

        create_reply = client.post(
            f"/api/v1/archive/documents/{document_id}/comments",
            json={"body": "Reply comment", "parent_id": root_id},
            headers=author["headers"],
        )
        assert create_reply.status_code == 200, create_reply.text
        reply_id = int((create_reply.json().get("item") or {}).get("id") or 0)
        assert reply_id > 0

        other_update = client.put(
            f"/api/v1/archive/documents/{document_id}/comments/{root_id}",
            json={"body": "Updated by non-author"},
            headers=other_user["headers"],
        )
        assert other_update.status_code == 403, other_update.text

        other_delete = client.delete(
            f"/api/v1/archive/documents/{document_id}/comments/{root_id}",
            headers=other_user["headers"],
        )
        assert other_delete.status_code == 403, other_delete.text

        viewer_create = client.post(
            f"/api/v1/archive/documents/{document_id}/comments",
            json={"body": "Viewer should not comment"},
            headers=viewer["headers"],
        )
        assert viewer_create.status_code == 403, viewer_create.text

        author_update = client.put(
            f"/api/v1/archive/documents/{document_id}/comments/{root_id}",
            json={"body": "Author edited comment"},
            headers=author["headers"],
        )
        assert author_update.status_code == 200, author_update.text
        assert (author_update.json().get("item") or {}).get("body") == "Author edited comment"

        author_delete = client.delete(
            f"/api/v1/archive/documents/{document_id}/comments/{root_id}",
            headers=author["headers"],
        )
        assert author_delete.status_code == 200, author_delete.text
        deleted_item = author_delete.json().get("item") or {}
        assert deleted_item.get("is_deleted") is True
        assert deleted_item.get("body") is None

        list_comments = client.get(f"/api/v1/archive/documents/{document_id}/comments", headers=admin)
        assert list_comments.status_code == 200, list_comments.text
        items = list_comments.json().get("items") or []
        by_id = _flatten_comment_ids(items)
        assert root_id in by_id
        assert reply_id in by_id
        assert by_id[root_id].get("is_deleted") is True
        assert by_id[root_id].get("body") is None

        actions = _get_activity_actions(document_id, admin)
        assert "comment_added" in actions
        assert "comment_updated" in actions
        assert "comment_deleted" in actions
    finally:
        _save_permission_scope(admin, "consultant", original_scope)
        _save_permission_matrix(admin, "consultant", original_matrix)


def test_document_comments_revision_filter_and_print_preview() -> None:
    admin = _admin_headers()
    document_id, doc_number = _register_document(admin, subject_prefix="CommentRevision")
    _upload_file(
        admin,
        document_id=document_id,
        filename="comment-revision.pdf",
        content=b"%PDF-1.4\n%comment-revision\n",
        mime_type="application/pdf",
        revision="00",
        status="IFA",
    )
    other_document_id, _ = _register_document(admin, subject_prefix="OtherCommentRevision")
    _upload_file(
        admin,
        document_id=other_document_id,
        filename="other-comment-revision.pdf",
        content=b"%PDF-1.4\n%other-comment-revision\n",
        mime_type="application/pdf",
        revision="00",
        status="IFA",
    )

    detail = client.get(f"/api/v1/archive/documents/{document_id}", headers=admin)
    assert detail.status_code == 200, detail.text
    revision_id = int(((detail.json().get("latest_revision") or {}).get("revision_id")) or 0)
    assert revision_id > 0

    other_detail = client.get(f"/api/v1/archive/documents/{other_document_id}", headers=admin)
    assert other_detail.status_code == 200, other_detail.text
    other_revision_id = int(((other_detail.json().get("latest_revision") or {}).get("revision_id")) or 0)
    assert other_revision_id > 0 and other_revision_id != revision_id

    general_comment = client.post(
        f"/api/v1/archive/documents/{document_id}/comments",
        json={"body": "Whole document note", "revision_id": None},
        headers=admin,
    )
    assert general_comment.status_code == 200, general_comment.text
    general_item = general_comment.json().get("item") or {}
    general_id = int(general_item.get("id") or 0)
    assert general_id > 0
    assert general_item.get("revision_id") is None
    assert general_item.get("revision_label")

    revision_comment = client.post(
        f"/api/v1/archive/documents/{document_id}/comments",
        json={"body": "Revision scoped note", "revision_id": revision_id},
        headers=admin,
    )
    assert revision_comment.status_code == 200, revision_comment.text
    revision_item = revision_comment.json().get("item") or {}
    revision_comment_id = int(revision_item.get("id") or 0)
    assert revision_comment_id > 0
    assert int(revision_item.get("revision_id") or 0) == revision_id
    assert revision_item.get("revision") == "00"
    assert "Rev 00" in str(revision_item.get("revision_label") or "")

    reply_comment = client.post(
        f"/api/v1/archive/documents/{document_id}/comments",
        json={"body": "Revision reply", "parent_id": revision_comment_id},
        headers=admin,
    )
    assert reply_comment.status_code == 200, reply_comment.text
    reply_item = reply_comment.json().get("item") or {}
    reply_id = int(reply_item.get("id") or 0)
    assert reply_id > 0
    assert int(reply_item.get("revision_id") or 0) == revision_id

    invalid_revision = client.post(
        f"/api/v1/archive/documents/{document_id}/comments",
        json={"body": "Wrong document revision", "revision_id": other_revision_id},
        headers=admin,
    )
    assert invalid_revision.status_code == 404, invalid_revision.text

    revision_list = client.get(
        f"/api/v1/archive/documents/{document_id}/comments?revision_id={revision_id}",
        headers=admin,
    )
    assert revision_list.status_code == 200, revision_list.text
    revision_by_id = _flatten_comment_ids(revision_list.json().get("items") or [])
    assert revision_comment_id in revision_by_id
    assert reply_id in revision_by_id
    assert general_id not in revision_by_id

    whole_document_list = client.get(
        f"/api/v1/archive/documents/{document_id}/comments?revision_id=0",
        headers=admin,
    )
    assert whole_document_list.status_code == 200, whole_document_list.text
    whole_by_id = _flatten_comment_ids(whole_document_list.json().get("items") or [])
    assert general_id in whole_by_id
    assert revision_comment_id not in whole_by_id

    print_preview = client.get(
        f"/api/v1/archive/documents/{document_id}/comments/print-preview?revision_id={revision_id}",
        headers=admin,
    )
    assert print_preview.status_code == 200, print_preview.text
    assert "text/html" in str(print_preview.headers.get("content-type") or "")
    assert doc_number in print_preview.text
    assert "Rev 00" in print_preview.text
    assert "Status" in print_preview.text
    assert "Printed At" in print_preview.text
    assert "Revision scoped note" in print_preview.text
    assert "Whole document note" not in print_preview.text

    delete_revision_comment = client.delete(
        f"/api/v1/archive/documents/{document_id}/comments/{revision_comment_id}",
        headers=admin,
    )
    assert delete_revision_comment.status_code == 200, delete_revision_comment.text

    print_after_delete = client.get(
        f"/api/v1/archive/documents/{document_id}/comments/print-preview?revision_id={revision_id}",
        headers=admin,
    )
    assert print_after_delete.status_code == 200, print_after_delete.text
    assert "Revision scoped note" not in print_after_delete.text
    assert "Revision reply" in print_after_delete.text


def test_document_relations_and_tags_with_duplicate_guards() -> None:
    admin = _admin_headers()
    source_document_id, _ = _register_document(admin, subject_prefix="RelSrc")
    target_document_id, _ = _register_document(admin, subject_prefix="RelDst")

    matrix_payload = _get_permission_matrix(admin, "consultant")
    original_matrix = deepcopy(matrix_payload.get("matrix") or {})
    available_permissions = {str(item) for item in (matrix_payload.get("permissions") or [])}
    modified_matrix = deepcopy(original_matrix)
    modified_matrix.setdefault("user", {})
    for permission in ("documents:relation_manage", "documents:tag_manage"):
        if permission in available_permissions:
            modified_matrix["user"][permission] = True

    scope_payload = _get_permission_scope(admin, "consultant")
    original_scope = deepcopy(scope_payload.get("scope") or {})
    modified_scope = deepcopy(original_scope)
    modified_scope.setdefault("user", {})
    user_projects = {str(code).strip().upper() for code in modified_scope["user"].get("projects", [])}
    user_disciplines = {str(code).strip().upper() for code in modified_scope["user"].get("disciplines", [])}
    user_projects.add(PROJECT_CODE)
    user_disciplines.add(DISCIPLINE_CODE)
    modified_scope["user"]["projects"] = sorted(user_projects)
    modified_scope["user"]["disciplines"] = sorted(user_disciplines)

    _save_permission_matrix(admin, "consultant", modified_matrix)
    _save_permission_scope(admin, "consultant", modified_scope)
    try:
        scoped_user = _create_scoped_user(
            admin,
            role="user",
            org_type="consultant",
            email_prefix="doc_relation_user",
        )
        scoped_headers = scoped_user["headers"]

        create_relation = client.post(
            f"/api/v1/archive/documents/{source_document_id}/relations",
            json={"target_document_id": target_document_id, "relation_type": "related", "notes": "linked"},
            headers=scoped_headers,
        )
        assert create_relation.status_code == 200, create_relation.text
        relation_id = int((create_relation.json().get("relation") or {}).get("id") or 0)
        assert relation_id > 0

        duplicate_relation = client.post(
            f"/api/v1/archive/documents/{source_document_id}/relations",
            json={"target_document_id": target_document_id, "relation_type": "related"},
            headers=scoped_headers,
        )
        assert duplicate_relation.status_code == 409, duplicate_relation.text

        self_relation = client.post(
            f"/api/v1/archive/documents/{source_document_id}/relations",
            json={"target_document_id": source_document_id, "relation_type": "related"},
            headers=scoped_headers,
        )
        assert self_relation.status_code == 400, self_relation.text

        remove_relation = client.delete(
            f"/api/v1/archive/documents/{source_document_id}/relations/{relation_id}",
            headers=scoped_headers,
        )
        assert remove_relation.status_code == 200, remove_relation.text

        delete_target = client.delete(f"/api/v1/archive/documents/{target_document_id}", headers=admin)
        assert delete_target.status_code == 200, delete_target.text

        deleted_target_relation = client.post(
            f"/api/v1/archive/documents/{source_document_id}/relations",
            json={"target_document_id": target_document_id, "relation_type": "related"},
            headers=scoped_headers,
        )
        assert deleted_target_relation.status_code == 404, deleted_target_relation.text

        create_tag = client.post(
            "/api/v1/archive/tags",
            json={"name": " QA-Tag ", "color": "#22AA88"},
            headers=scoped_headers,
        )
        assert create_tag.status_code == 200, create_tag.text
        tag_id = int((create_tag.json().get("tag") or {}).get("id") or 0)
        assert tag_id > 0
        assert (create_tag.json().get("tag") or {}).get("scope") == "document"

        reused_tag = client.post(
            "/api/v1/archive/tags",
            json={"name": "qa-tag"},
            headers=scoped_headers,
        )
        assert reused_tag.status_code == 200, reused_tag.text
        assert int((reused_tag.json().get("tag") or {}).get("id") or 0) == tag_id
        assert (reused_tag.json().get("tag") or {}).get("scope") == "document"

        assign_tag = client.post(
            f"/api/v1/archive/documents/{source_document_id}/tags",
            json={"tag_id": tag_id},
            headers=scoped_headers,
        )
        assert assign_tag.status_code == 200, assign_tag.text

        duplicate_assign = client.post(
            f"/api/v1/archive/documents/{source_document_id}/tags",
            json={"tag_id": tag_id},
            headers=scoped_headers,
        )
        assert duplicate_assign.status_code == 409, duplicate_assign.text

        list_tags = client.get(f"/api/v1/archive/documents/{source_document_id}/tags", headers=scoped_headers)
        assert list_tags.status_code == 200, list_tags.text
        tag_items = list_tags.json().get("items") or []
        assert any(int(item.get("tag_id") or 0) == tag_id for item in tag_items)

        remove_tag = client.delete(
            f"/api/v1/archive/documents/{source_document_id}/tags/{tag_id}",
            headers=scoped_headers,
        )
        assert remove_tag.status_code == 200, remove_tag.text

        actions = _get_activity_actions(source_document_id, admin)
        assert "relation_added" in actions
        assert "relation_removed" in actions
        assert "tag_added" in actions
        assert "tag_removed" in actions
    finally:
        _save_permission_scope(admin, "consultant", original_scope)
        _save_permission_matrix(admin, "consultant", original_matrix)


def test_document_relations_accept_codes_for_documents_correspondence_minutes_and_forms() -> None:
    admin = _admin_headers()
    _ensure_reclassify_lookups(admin)
    source_document_id, _ = _register_document(admin, subject_prefix="RelMixedSrc")
    target_document_id, target_doc_number = _register_document(admin, subject_prefix="RelMixedDoc")

    document_relation = client.post(
        f"/api/v1/archive/documents/{source_document_id}/relations",
        json={"target_entity_type": "document", "target_code": target_doc_number, "relation_type": "references"},
        headers=admin,
    )
    assert document_relation.status_code == 200, document_relation.text
    document_relation_body = document_relation.json().get("relation") or {}
    assert document_relation_body.get("target_entity_type") == "document"
    assert document_relation_body.get("target_document_id") == target_document_id
    assert (document_relation_body.get("counterpart") or {}).get("doc_number") == target_doc_number

    reference_no = f"{PROJECT_CODE}-CO-O-{uuid4().hex[:6].upper()}"
    correspondence_res = client.post(
        "/api/v1/correspondence/create",
        json={
            "project_code": PROJECT_CODE,
            "issuing_code": PROJECT_CODE,
            "category_code": "CO",
            "discipline_code": DISCIPLINE_CODE,
            "doc_type": "Correspondence",
            "direction": "O",
            "reference_no": reference_no,
            "subject": "Relation correspondence target",
            "sender": "DCC",
            "recipient": "Engineering",
            "status": "Open",
            "priority": "Normal",
        },
        headers=admin,
    )
    assert correspondence_res.status_code == 200, correspondence_res.text

    meeting_no = f"{PROJECT_CODE}-MOM-{uuid4().hex[:6].upper()}"
    minute_res = client.post(
        "/api/v1/meeting-minutes/create",
        json={
            "meeting_no": meeting_no,
            "title": "Relation meeting target",
            "project_code": PROJECT_CODE,
            "meeting_type": "Coordination",
            "status": "Open",
        },
        headers=admin,
    )
    assert minute_res.status_code == 200, minute_res.text

    rfi_no = f"{PROJECT_CODE}-RFI-{uuid4().hex[:6].upper()}"
    ncr_no = f"{PROJECT_CODE}-NCR-{uuid4().hex[:6].upper()}"
    site_log_no = f"{PROJECT_CODE}-SLOG-{uuid4().hex[:6].upper()}"
    permit_no = f"{PROJECT_CODE}-PQC-{uuid4().hex[:6].upper()}"
    with SessionLocal() as db:
        db.add_all(
            [
                CommItem(
                    item_no=rfi_no,
                    item_type="RFI",
                    project_code=PROJECT_CODE,
                    discipline_code=DISCIPLINE_CODE,
                    title="Relation RFI target",
                    status_code="OPEN",
                    priority="NORMAL",
                ),
                CommItem(
                    item_no=ncr_no,
                    item_type="NCR",
                    project_code=PROJECT_CODE,
                    discipline_code=DISCIPLINE_CODE,
                    title="Relation NCR target",
                    status_code="ISSUED",
                    priority="NORMAL",
                ),
                SiteLog(
                    log_no=site_log_no,
                    log_type="DAILY",
                    project_code=PROJECT_CODE,
                    discipline_code=DISCIPLINE_CODE,
                    log_date=datetime.utcnow(),
                    current_work_summary="Relation site log target",
                    status_code="SUBMITTED",
                ),
                PermitQcPermit(
                    permit_no=permit_no,
                    permit_date=datetime.utcnow(),
                    title="Relation permit QC target",
                    status_code="SUBMITTED",
                    project_code=PROJECT_CODE,
                    discipline_code=DISCIPLINE_CODE,
                ),
            ]
        )
        db.commit()

    corr_relation = client.post(
        f"/api/v1/archive/documents/{source_document_id}/relations",
        json={"target_entity_type": "correspondence", "target_code": reference_no, "relation_type": "related"},
        headers=admin,
    )
    assert corr_relation.status_code == 200, corr_relation.text
    corr_relation_body = corr_relation.json().get("relation") or {}
    assert corr_relation_body.get("target_entity_type") == "correspondence"
    assert corr_relation_body.get("target_code") == reference_no
    assert str(corr_relation_body.get("id") or "").startswith("external:")

    minute_relation = client.post(
        f"/api/v1/archive/documents/{source_document_id}/relations",
        json={"target_entity_type": "meeting_minute", "target_code": meeting_no, "relation_type": "references"},
        headers=admin,
    )
    assert minute_relation.status_code == 200, minute_relation.text
    minute_relation_body = minute_relation.json().get("relation") or {}
    assert minute_relation_body.get("target_entity_type") == "meeting_minute"
    assert minute_relation_body.get("target_code") == meeting_no

    rfi_relation = client.post(
        f"/api/v1/archive/documents/{source_document_id}/relations",
        json={"target_entity_type": "rfi", "target_code": rfi_no, "relation_type": "references"},
        headers=admin,
    )
    assert rfi_relation.status_code == 200, rfi_relation.text
    assert (rfi_relation.json().get("relation") or {}).get("target_entity_type") == "rfi"

    ncr_relation = client.post(
        f"/api/v1/archive/documents/{source_document_id}/relations",
        json={"target_entity_type": "ncr", "target_code": ncr_no, "relation_type": "related"},
        headers=admin,
    )
    assert ncr_relation.status_code == 200, ncr_relation.text
    assert (ncr_relation.json().get("relation") or {}).get("target_entity_type") == "ncr"

    site_log_relation = client.post(
        f"/api/v1/archive/documents/{source_document_id}/relations",
        json={"target_entity_type": "site_log", "target_code": site_log_no, "relation_type": "related"},
        headers=admin,
    )
    assert site_log_relation.status_code == 200, site_log_relation.text
    assert (site_log_relation.json().get("relation") or {}).get("target_entity_type") == "site_log"

    permit_relation = client.post(
        f"/api/v1/archive/documents/{source_document_id}/relations",
        json={"target_entity_type": "permit_qc", "target_code": permit_no, "relation_type": "related"},
        headers=admin,
    )
    assert permit_relation.status_code == 200, permit_relation.text
    assert (permit_relation.json().get("relation") or {}).get("target_entity_type") == "permit_qc"

    duplicate_corr_relation = client.post(
        f"/api/v1/archive/documents/{source_document_id}/relations",
        json={"target_entity_type": "correspondence", "target_code": reference_no, "relation_type": "related"},
        headers=admin,
    )
    assert duplicate_corr_relation.status_code == 409, duplicate_corr_relation.text

    detail_res = client.get(f"/api/v1/archive/documents/{source_document_id}", headers=admin)
    assert detail_res.status_code == 200, detail_res.text
    outgoing = ((detail_res.json().get("relations") or {}).get("outgoing") or [])
    indexed = {
        (str(row.get("target_entity_type") or ""), str(row.get("target_code") or "")): row
        for row in outgoing
    }
    assert ("document", target_doc_number) in indexed
    assert ("correspondence", reference_no) in indexed
    assert ("meeting_minute", meeting_no) in indexed
    assert ("rfi", rfi_no) in indexed
    assert ("ncr", ncr_no) in indexed
    assert ("site_log", site_log_no) in indexed
    assert ("permit_qc", permit_no) in indexed

    remove_external = client.delete(
        f"/api/v1/archive/documents/{source_document_id}/relations/{corr_relation_body.get('id')}",
        headers=admin,
    )
    assert remove_external.status_code == 200, remove_external.text

    relations_after_delete = client.get(f"/api/v1/archive/documents/{source_document_id}/relations", headers=admin)
    assert relations_after_delete.status_code == 200, relations_after_delete.text
    outgoing_after = relations_after_delete.json().get("outgoing") or []
    assert all(str(row.get("target_code") or "") != reference_no for row in outgoing_after)


def test_document_transmittal_linkage_and_activity() -> None:
    admin = _admin_headers()
    document_id, doc_number = _register_document(admin, subject_prefix="TransLink")
    _upload_file(
        admin,
        document_id=document_id,
        filename="transmittal.pdf",
        content=b"%PDF-1.4\n%transmittal\n",
        mime_type="application/pdf",
    )

    create_transmittal = client.post(
        "/api/v1/transmittal/create",
        json={
            "project_code": PROJECT_CODE,
            "sender": "O",
            "receiver": "C",
            "documents": [
                {
                    "document_code": doc_number,
                    "revision": "00",
                    "status": "IFA",
                    "electronic_copy": True,
                    "hard_copy": False,
                }
            ],
            "issue_now": True,
        },
        headers=admin,
    )
    assert create_transmittal.status_code == 200, create_transmittal.text
    transmittal_no = str(create_transmittal.json().get("transmittal_no") or "").strip()
    assert transmittal_no

    linked_transmittals = client.get(f"/api/v1/archive/documents/{document_id}/transmittals", headers=admin)
    assert linked_transmittals.status_code == 200, linked_transmittals.text
    rows = linked_transmittals.json().get("data") or []
    assert any(str(row.get("id") or "") == transmittal_no for row in rows)

    actions = _get_activity_actions(document_id, admin)
    assert "transmittal_sent" in actions
