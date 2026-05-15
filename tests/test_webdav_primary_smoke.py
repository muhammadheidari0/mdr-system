from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.models import Discipline, Organization, Project
from app.db.session import SessionLocal
from app.main import app
from app.services.file_integrity import SavedFileInfo
from app.services.storage import StorageManager
from tests.auth_helpers import get_auth_headers
from tests.site_logs_helpers import ensure_org, ensure_project_discipline


client = TestClient(app)


class _FakeWebdavAdapter:
    def __init__(self) -> None:
        self.deleted_paths: list[str] = []
        self.downloaded_paths: list[str] = []
        self.existing_paths: set[str] = set()

    def file_exists(self, remote_relative_path: str) -> bool:
        return str(remote_relative_path) in self.existing_paths

    def download_file_stream(self, remote_relative_path: str):
        self.downloaded_paths.append(str(remote_relative_path))
        yield b"webdav-stream-content"

    def delete_file(self, remote_relative_path: str) -> bool:
        self.deleted_paths.append(str(remote_relative_path))
        return True


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


@pytest.fixture
def webdav_primary(monkeypatch: pytest.MonkeyPatch) -> _FakeWebdavAdapter:
    adapter = _FakeWebdavAdapter()

    def _fake_save_upload_to_webdav(self, *, file, remote_relative_path: str, file_kind: str = "attachment"):
        filename = str(getattr(file, "filename", "") or "upload.bin").strip() or "upload.bin"
        adapter.existing_paths.add(str(remote_relative_path))
        return SavedFileInfo(
            stored_path=f"webdav://{remote_relative_path}",
            size_bytes=128,
            sha256="deadbeef",
            detected_mime=str(getattr(file, "content_type", "") or "application/octet-stream"),
            declared_mime=str(getattr(file, "content_type", "") or "application/octet-stream"),
            validation_status="valid",
            original_name=filename,
            validation_notes="",
        )

    monkeypatch.setattr(StorageManager, "_is_webdav_primary_mode", lambda self: True)
    monkeypatch.setattr(StorageManager, "save_upload_to_webdav", _fake_save_upload_to_webdav)
    monkeypatch.setattr(StorageManager, "resolve_storage_backend_for_path", lambda self, path: "nextcloud")
    monkeypatch.setattr(StorageManager, "get_mdr_webdav_base", lambda self: "/ARCA-NTN/MDR")
    monkeypatch.setattr(StorageManager, "get_correspondence_webdav_base", lambda self: "/ARCA-NTN/Correspondence")
    monkeypatch.setattr(StorageManager, "get_site_log_webdav_base", lambda self: "/ARCA-NTN/SiteLogs")

    fake_runtime = {
        "enabled": True,
        "mode": "webdav",
        "base_url": "https://nextcloud.invalid",
        "username": "integration",
        "app_password": "secret",
        "root_path": "/ARCA-NTN",
        "connect_timeout": 5,
        "read_timeout": 10,
        "tls_verify": True,
    }

    from app.api.v1.routers import archive as archive_router
    from app.api.v1.routers import communication_items as comm_router
    from app.api.v1.routers import correspondence as corr_router
    from app.api.v1.routers import permit_qc as permit_router
    from app.api.v1.routers import site_logs as site_logs_router
    from app.api.v1.routers import storage as storage_router

    monkeypatch.setattr(corr_router, "_nextcloud_adapter_for_webdav", lambda db: adapter)
    monkeypatch.setattr(comm_router, "_nextcloud_adapter_for_webdav", lambda db: adapter)
    monkeypatch.setattr(site_logs_router, "_nextcloud_adapter_for_webdav", lambda db: adapter)
    monkeypatch.setattr(permit_router, "_nextcloud_adapter_for_webdav", lambda db: adapter)
    monkeypatch.setattr(archive_router, "get_storage_integrations", lambda db: {})
    monkeypatch.setattr(archive_router, "resolve_nextcloud_runtime", lambda integrations: fake_runtime)
    monkeypatch.setattr(archive_router, "NextcloudAdapter", lambda **kwargs: adapter)
    monkeypatch.setattr(storage_router, "get_storage_integrations", lambda db: {})
    monkeypatch.setattr(storage_router, "resolve_nextcloud_runtime", lambda integrations: fake_runtime)
    monkeypatch.setattr(storage_router, "NextcloudAdapter", lambda **kwargs: adapter)
    return adapter


def _create_correspondence(headers: dict[str, str]) -> int:
    project_code = f"WC{uuid.uuid4().hex[:6].upper()}"
    with SessionLocal() as db:
        project = db.query(Project).filter(Project.code == project_code).first()
        if not project:
            db.add(Project(code=project_code, name_e=f"WebDAV Corr {project_code}", is_active=True))
            db.commit()
    create_res = client.post(
        "/api/v1/correspondence/create",
        json={
            "project_code": project_code,
            "issuing_code": project_code,
            "category_code": "CO",
            "doc_type": "Correspondence",
            "direction": "O",
            "reference_no": f"{project_code}-CO-O-2604001",
            "subject": f"WebDAV Corr {project_code}",
            "status": "Open",
        },
        headers=headers,
    )
    assert create_res.status_code == 200, create_res.text
    return int(create_res.json().get("data", {}).get("id") or 0)


def _create_comm_item(headers: dict[str, str]) -> int:
    project_code, discipline_code = ensure_project_discipline(client, headers)
    recipient_org_id = ensure_org(client, headers, org_type="consultant", code_prefix="WDVCONS")
    due = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%dT00:00:00")
    res = client.post(
        "/api/v1/comm-items/create",
        json={
            "item_type": "RFI",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "title": f"WebDAV RFI {uuid.uuid4().hex[:6]}",
            "status_code": "DRAFT",
            "priority": "NORMAL",
            "response_due_date": due,
            "recipient_org_id": recipient_org_id,
            "rfi": {
                "question_text": "WebDAV question",
                "proposed_solution": "WebDAV proposal",
            },
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return int(res.json().get("data", {}).get("id") or 0)


def _create_site_log(headers: dict[str, str]) -> int:
    project_code, discipline_code = ensure_project_discipline(client, headers)
    organization_id = ensure_org(client, headers, org_type="contractor", code_prefix="WDVSLOG")
    res = client.post(
        "/api/v1/site-logs/create",
        json={
            "log_type": "DAILY",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "organization_id": organization_id,
            "log_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
            "weather": "CLEAR",
            "summary": "WebDAV site log",
            "manpower_rows": [
                {
                    "role_code": "FOREMAN",
                    "role_label": "Foreman",
                    "claimed_count": 2,
                    "claimed_hours": 8.0,
                    "sort_order": 0,
                }
            ],
            "equipment_rows": [],
            "activity_rows": [],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return int(res.json().get("data", {}).get("id") or 0)


def _create_permit(headers: dict[str, str]) -> int:
    project_code = f"WP{uuid.uuid4().hex[:6]}".upper()
    discipline_code = f"WD{uuid.uuid4().hex[:4]}".upper()
    consultant_code = f"CONS_{uuid.uuid4().hex[:8]}".upper()
    with SessionLocal() as db:
        if not db.query(Project).filter(Project.code == project_code).first():
            db.add(Project(code=project_code, name_e=f"Permit {project_code}", is_active=True))
        if not db.query(Discipline).filter(Discipline.code == discipline_code).first():
            db.add(Discipline(code=discipline_code, name_e=f"Discipline {discipline_code}", name_p=f"Discipline {discipline_code}"))
        consultant_org = db.query(Organization).filter(Organization.code == consultant_code).first()
        if not consultant_org:
            consultant_org = Organization(code=consultant_code, name=f"Consultant {consultant_code}", org_type="consultant", is_active=True)
            db.add(consultant_org)
        db.commit()
        db.refresh(consultant_org)
        consultant_org_id = int(consultant_org.id)

    template_code = f"TPL_{uuid.uuid4().hex[:7]}".upper()
    create_template = client.post(
        "/api/v1/permit-qc/templates/upsert",
        headers=headers,
        json={
            "code": template_code,
            "name": f"Template {template_code}",
            "description": "WebDAV permit template",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "is_active": True,
            "is_default": True,
        },
    )
    assert create_template.status_code == 200, create_template.text
    template_id = int((create_template.json().get("data") or {}).get("id") or 0)
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

    permit_no = f"{project_code}-PERMIT-{uuid.uuid4().hex[:6]}".upper()
    create_res = client.post(
        "/api/v1/permit-qc/create",
        headers=headers,
        json={
            "module_key": "contractor",
            "permit_no": permit_no,
            "permit_date": "2026-02-28T00:00:00",
            "title": "WebDAV permit",
            "description": "permit webdav",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "template_id": template_id,
            "consultant_org_id": consultant_org_id,
        },
    )
    assert create_res.status_code == 200, create_res.text
    return int((create_res.json().get("data") or {}).get("id") or 0)


def test_webdav_primary_correspondence_attachment_flow(admin_headers: dict[str, str], webdav_primary: _FakeWebdavAdapter) -> None:
    correspondence_id = _create_correspondence(admin_headers)
    upload_res = client.post(
        f"/api/v1/correspondence/{correspondence_id}/attachments/upload",
        data={"file_kind": "letter"},
        files={"file": ("corr.pdf", io.BytesIO(b"%PDF-1.4\ncorr-preview\n"), "application/pdf")},
        headers=admin_headers,
    )
    assert upload_res.status_code == 200, upload_res.text
    attachment = upload_res.json().get("data") or {}
    attachment_id = int(attachment.get("id") or 0)
    assert attachment_id > 0
    assert attachment.get("file_kind") == "letter"

    download_res = client.get(f"/api/v1/correspondence/attachments/{attachment_id}/download", headers=admin_headers)
    assert download_res.status_code == 200, download_res.text
    assert download_res.content == b"webdav-stream-content"

    preview_res = client.get(f"/api/v1/correspondence/{correspondence_id}/preview", headers=admin_headers)
    assert preview_res.status_code == 200, preview_res.text
    assert preview_res.content == b"webdav-stream-content"
    assert "inline;" in str(preview_res.headers.get("content-disposition") or "").lower()

    delete_res = client.delete(f"/api/v1/correspondence/attachments/{attachment_id}", headers=admin_headers)
    assert delete_res.status_code == 200, delete_res.text
    assert webdav_primary.deleted_paths


def test_webdav_primary_comm_items_attachment_flow(admin_headers: dict[str, str], webdav_primary: _FakeWebdavAdapter) -> None:
    item_id = _create_comm_item(admin_headers)
    upload_res = client.post(
        f"/api/v1/comm-items/{item_id}/attachments",
        data={"file_kind": "attachment", "scope_code": "REFERENCE", "slot_code": "RFI_REFERENCE"},
        files={"file": ("comm.txt", io.BytesIO(b"comm-content"), "text/plain")},
        headers=admin_headers,
    )
    assert upload_res.status_code == 200, upload_res.text
    attachment = upload_res.json().get("data") or {}
    attachment_id = int(attachment.get("id") or 0)
    assert str(attachment.get("stored_path") or "").startswith("webdav://")

    download_res = client.get(f"/api/v1/comm-items/attachments/{attachment_id}/download", headers=admin_headers)
    assert download_res.status_code == 200, download_res.text
    assert download_res.content == b"webdav-stream-content"

    delete_res = client.delete(
        f"/api/v1/comm-items/{item_id}/attachments",
        params={"attachment_id": attachment_id},
        headers=admin_headers,
    )
    assert delete_res.status_code == 200, delete_res.text
    assert webdav_primary.deleted_paths


def test_webdav_primary_site_logs_attachment_flow(admin_headers: dict[str, str], webdav_primary: _FakeWebdavAdapter) -> None:
    log_id = _create_site_log(admin_headers)
    upload_res = client.post(
        f"/api/v1/site-logs/{log_id}/attachments",
        data={"file_kind": "attachment", "section_code": "GENERAL"},
        files={"file": ("log.txt", io.BytesIO(b"log-content"), "text/plain")},
        headers=admin_headers,
    )
    assert upload_res.status_code == 200, upload_res.text
    attachment = upload_res.json().get("data") or {}
    attachment_id = int(attachment.get("id") or 0)
    assert str(attachment.get("stored_path") or "").startswith("webdav://")

    download_res = client.get(f"/api/v1/site-logs/attachments/{attachment_id}/download", headers=admin_headers)
    assert download_res.status_code == 200, download_res.text
    assert download_res.content == b"webdav-stream-content"

    delete_res = client.delete(
        f"/api/v1/site-logs/{log_id}/attachments",
        params={"attachment_id": attachment_id},
        headers=admin_headers,
    )
    assert delete_res.status_code == 200, delete_res.text
    assert webdav_primary.deleted_paths


def test_webdav_primary_permit_qc_attachment_flow(admin_headers: dict[str, str], webdav_primary: _FakeWebdavAdapter) -> None:
    permit_id = _create_permit(admin_headers)
    upload_res = client.post(
        f"/api/v1/permit-qc/{permit_id}/attachments",
        data={"module_key": "contractor", "file_kind": "attachment"},
        files={"file": ("permit.pdf", io.BytesIO(b"%PDF-1.4 permit"), "application/pdf")},
        headers=admin_headers,
    )
    assert upload_res.status_code == 200, upload_res.text
    attachment = upload_res.json().get("data") or {}
    attachment_id = int(attachment.get("id") or 0)
    assert str(attachment.get("stored_path") or "").startswith("webdav://")

    download_res = client.get(
        f"/api/v1/permit-qc/attachments/{attachment_id}/download",
        params={"module_key": "contractor"},
        headers=admin_headers,
    )
    assert download_res.status_code == 200, download_res.text
    assert download_res.content == b"webdav-stream-content"

    delete_res = client.delete(
        f"/api/v1/permit-qc/{permit_id}/attachments",
        params={"module_key": "contractor", "attachment_id": attachment_id},
        headers=admin_headers,
    )
    assert delete_res.status_code == 200, delete_res.text
    assert webdav_primary.deleted_paths


def test_webdav_primary_archive_upload_and_download_flow(admin_headers: dict[str, str], webdav_primary: _FakeWebdavAdapter) -> None:
    project_code = f"WA{uuid.uuid4().hex[:6].upper()}"
    with SessionLocal() as db:
        if not db.query(Project).filter(Project.code == project_code).first():
            db.add(Project(code=project_code, name_e=f"Archive {project_code}", is_active=True))
            db.commit()

    register_res = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": f"{project_code}-EGN0001-TGEN",
            "project_code": project_code,
            "mdr_code": "E",
            "phase": "X",
            "discipline": "GN",
            "package": "00",
            "block": "T",
            "level": "GEN",
            "subject_e": f"Archive WebDAV {uuid.uuid4().hex[:6]}",
        },
        headers=admin_headers,
    )
    assert register_res.status_code == 200, register_res.text
    document_id = int(register_res.json().get("document_id") or 0)
    assert document_id > 0

    upload_res = client.post(
        "/api/v1/archive/upload",
        data={
            "document_id": str(document_id),
            "revision": "00",
            "status": "IFA",
            "file_kind": "pdf",
        },
        files={"file": ("archive.pdf", io.BytesIO(b"%PDF-1.4\narchive-webdav\n"), "application/pdf")},
        headers=admin_headers,
    )
    assert upload_res.status_code == 200, upload_res.text
    file_id = int(upload_res.json().get("file_id") or 0)
    assert file_id > 0
    remote_path = next(iter(webdav_primary.existing_paths))
    expected_project_folder = f"{project_code} - Archive {project_code}"
    assert remote_path.startswith(f"/MDR/{expected_project_folder}/")
    assert "/GN/" in remote_path
    assert "/pdf/" in remote_path

    download_res = client.get(f"/api/v1/archive/download/{file_id}", headers=admin_headers)
    assert download_res.status_code == 200, download_res.text
    assert download_res.content == b"webdav-stream-content"

    detail_res = client.get(f"/api/v1/archive/documents/{document_id}", headers=admin_headers)
    assert detail_res.status_code == 200, detail_res.text

    preview_res = client.get(f"/api/v1/archive/documents/{document_id}/preview", headers=admin_headers)
    assert preview_res.status_code == 200, preview_res.text
    assert preview_res.content == b"webdav-stream-content"
    assert "inline;" in str(preview_res.headers.get("content-disposition") or "").lower()


def test_webdav_primary_site_agent_download_flow(admin_headers: dict[str, str], webdav_primary: _FakeWebdavAdapter) -> None:
    project_code = "TSEED"
    doc_number = f"{project_code}-EGN{uuid.uuid4().hex[:4].upper()}01-TGEN"

    register = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": doc_number,
            "project_code": project_code,
            "mdr_code": "E",
            "phase": "X",
            "discipline": "GN",
            "package": "00",
            "block": "T",
            "level": "GEN",
            "subject_e": f"Site Agent WebDAV {uuid.uuid4().hex[:6]}",
        },
        headers=admin_headers,
    )
    assert register.status_code == 200, register.text
    document_id = int(register.json().get("document_id") or 0)
    assert document_id > 0

    upload = client.post(
        "/api/v1/archive/upload",
        data={
            "document_id": str(document_id),
            "revision": "00",
            "status": "IFA",
            "file_kind": "pdf",
        },
        files={"file": ("site.pdf", io.BytesIO(b"%PDF-1.4\nsite-agent-webdav\n"), "application/pdf")},
        headers=admin_headers,
    )
    assert upload.status_code == 200, upload.text
    file_id = int(upload.json().get("file_id") or 0)
    assert file_id > 0

    profile_code = f"SITE_{uuid.uuid4().hex[:8].upper()}"
    profile_res = client.post(
        "/api/v1/settings/site-cache/profiles/upsert",
        json={
            "code": profile_code,
            "name": f"Site {profile_code}",
            "project_code": project_code,
            "local_root_path": r"\\\\site-server\\mdr_cache",
            "fallback_mode": "local_first",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert profile_res.status_code == 200, profile_res.text
    profile_id = int(profile_res.json().get("item", {}).get("id") or 0)
    assert profile_id > 0

    cidr_res = client.post(
        "/api/v1/settings/site-cache/cidrs/upsert",
        json={"profile_id": profile_id, "cidr": "10.199.0.0/16", "is_active": True},
        headers=admin_headers,
    )
    assert cidr_res.status_code == 200, cidr_res.text

    rule_res = client.post(
        "/api/v1/settings/site-cache/rules/upsert",
        json={
            "profile_id": profile_id,
            "name": "webdav site-agent rule",
            "project_code": project_code,
            "status_codes": "IFA",
            "include_native": False,
            "primary_only": True,
            "latest_revision_only": True,
            "priority": 1,
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert rule_res.status_code == 200, rule_res.text

    mint_res = client.post(
        "/api/v1/settings/site-cache/tokens/mint",
        json={"profile_id": profile_id},
        headers=admin_headers,
    )
    assert mint_res.status_code == 200, mint_res.text
    token = str(mint_res.json().get("token") or "").strip()
    assert token

    rebuild_res = client.post(
        "/api/v1/settings/site-cache/rebuild-pins",
        json={"profile_id": profile_id, "dry_run": False},
        headers=admin_headers,
    )
    assert rebuild_res.status_code == 200, rebuild_res.text

    site_headers = {"Authorization": f"Bearer {token}"}
    download_res = client.get(
        f"/api/v1/storage/site-agent/download/{file_id}",
        params={"site_code": profile_code},
        headers=site_headers,
    )
    assert download_res.status_code == 200, download_res.text
    assert download_res.content == b"webdav-stream-content"
