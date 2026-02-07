from __future__ import annotations

import uuid
import io
import os
import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.main import app
from app.db.models import MdrDocument
from app.db.session import engine
from tests.auth_helpers import get_auth_headers

client = TestClient(app)


@pytest.fixture(scope="module")
def admin_headers() -> dict[str, str]:
    """Use the central auth helper for admin token."""
    return get_auth_headers(client)


def test_regression_search_params(admin_headers: dict[str, str]) -> None:
    """
    Frontend doc_search sends `doc` and `size`.
    Backend should accept these params and return list payload.
    """
    response = client.get("/api/v1/mdr/search?doc=T202&size=5", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert isinstance(data["items"], list)


def test_regression_user_update_payload(admin_headers: dict[str, str]) -> None:
    """
    Frontend users PUT sends only full_name/role/is_active (no password/email).
    Backend should accept this payload.
    """
    users_res = client.get("/api/v1/users/", headers=admin_headers)
    assert users_res.status_code == 200, users_res.text
    users = users_res.json()
    if not users:
        pytest.skip("No users found for update regression test")

    target_user = next((u for u in users if u.get("role") != "admin"), users[0])
    user_id = target_user["id"]
    new_name = f"Regression Update {uuid.uuid4().hex[:6]}"

    payload = {
        "full_name": new_name,
        "role": target_user["role"],
        "is_active": target_user["is_active"],
    }
    response = client.put(f"/api/v1/users/{user_id}", json=payload, headers=admin_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == new_name


def test_regression_settings_init_fallback(admin_headers: dict[str, str]) -> None:
    """
    Settings UI reads projects from lookup/dictionary and expects a project name key.
    """
    response = client.get("/api/v1/lookup/dictionary", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("ok") is True
    projects = data.get("data", {}).get("projects", [])

    if projects:
        project = projects[0]
        assert any(key in project for key in ("project_name", "name", "name_e"))


def test_regression_auth_navigation_edms_tabs(admin_headers: dict[str, str]) -> None:
    res = client.get("/api/v1/auth/navigation", headers=admin_headers)
    if res.status_code == 429:
        pytest.skip("Rate limit middleware reached during auth navigation test")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    tabs = body.get("edms_tabs", {})
    assert isinstance(tabs, dict)
    for key in ("archive", "transmittal", "correspondence", "reports"):
        assert key in tabs
        assert isinstance(tabs[key], bool)
    default_tab = body.get("default_edms_tab")
    assert default_tab in ("archive", "transmittal", "correspondence", "reports")
    assert tabs.get(default_tab) is True


def test_regression_settings_storage_paths_roundtrip(admin_headers: dict[str, str]) -> None:
    get_res = client.get("/api/v1/settings/storage-paths", headers=admin_headers)
    if get_res.status_code == 429:
        pytest.skip("Rate limit middleware reached during storage paths test")
    assert get_res.status_code == 200, get_res.text
    before = get_res.json()
    assert before.get("ok") is True

    payload = {
        "mdr_storage_path": f"./files/technical_{uuid.uuid4().hex[:6]}",
        "correspondence_storage_path": f"./files/correspondence_{uuid.uuid4().hex[:6]}",
    }

    try:
        save_res = client.post(
            "/api/v1/settings/storage-paths",
            json=payload,
            headers=admin_headers,
        )
        assert save_res.status_code == 200, save_res.text
        save_body = save_res.json()
        assert save_body.get("ok") is True
        assert save_body.get("mdr_storage_path") == payload["mdr_storage_path"]
        assert save_body.get("correspondence_storage_path") == payload["correspondence_storage_path"]

        verify_res = client.get("/api/v1/settings/storage-paths", headers=admin_headers)
        assert verify_res.status_code == 200, verify_res.text
        verify_body = verify_res.json()
        assert verify_body.get("mdr_storage_path") == payload["mdr_storage_path"]
        assert verify_body.get("correspondence_storage_path") == payload["correspondence_storage_path"]
    finally:
        restore_payload = {
            "mdr_storage_path": before.get("mdr_storage_path") or "./files/technical",
            "correspondence_storage_path": before.get("correspondence_storage_path") or "./files/correspondence",
        }
        restore_res = client.post(
            "/api/v1/settings/storage-paths",
            json=restore_payload,
            headers=admin_headers,
        )
        assert restore_res.status_code == 200, restore_res.text


def test_regression_archive_files_dual_file_columns_exist() -> None:
    with engine.connect() as conn:
        table_row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='archive_files'")
        ).fetchone()
        if not table_row:
            pytest.skip("archive_files table is not available in current database")

        columns = conn.execute(text("PRAGMA table_info(archive_files)")).fetchall()
        column_names = {str(row[1]) for row in columns}

    assert "file_kind" in column_names
    assert "is_primary" in column_names
    assert "companion_file_id" in column_names


def test_regression_correspondence_tables_exist() -> None:
    with engine.connect() as conn:
        table_names = {
            str(row[0])
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }

    required_tables = {
        "correspondences",
        "correspondence_actions",
        "correspondence_attachments",
        "issuing_entities",
        "correspondence_categories",
    }
    if not required_tables.issubset(table_names):
        from app.db.session import init_db

        init_db()
        with engine.connect() as conn:
            table_names = {
                str(row[0])
                for row in conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).fetchall()
            }

    with engine.connect() as conn:
        
        assert required_tables.issubset(table_names)

        corr_columns = {
            str(row[1]) for row in conn.execute(text("PRAGMA table_info(correspondences)")).fetchall()
        }
        action_columns = {
            str(row[1]) for row in conn.execute(text("PRAGMA table_info(correspondence_actions)")).fetchall()
        }
        attachment_columns = {
            str(row[1]) for row in conn.execute(text("PRAGMA table_info(correspondence_attachments)")).fetchall()
        }
        corr_indexes = {
            str(row[1]): int(row[2])
            for row in conn.execute(text("PRAGMA index_list(correspondences)")).fetchall()
        }

    for required in (
        "project_code",
        "issuing_code",
        "category_code",
        "discipline_code",
        "doc_type",
        "direction",
        "reference_no",
        "subject",
        "status",
        "created_by_id",
    ):
        assert required in corr_columns

    for required in (
        "correspondence_id",
        "action_type",
        "from_user_id",
        "to_user_id",
        "status",
        "is_closed",
    ):
        assert required in action_columns

    for required in (
        "correspondence_id",
        "action_id",
        "file_name",
        "stored_path",
        "uploaded_by_id",
    ):
        assert required in attachment_columns
    assert "uq_correspondences_reference_no" in corr_indexes
    assert int(corr_indexes["uq_correspondences_reference_no"]) == 1


def test_regression_correspondence_c2_router_flow() -> None:
    from types import SimpleNamespace

    from app.api.v1.routers.correspondence import (
        CorrespondenceCreateIn,
        CorrespondenceUpdateIn,
        create_correspondence,
        get_correspondence_dashboard,
        list_correspondence,
        update_correspondence,
    )
    from app.db.models import Correspondence, Project

    project_code = f"CP{uuid.uuid4().hex[:6].upper()}"
    created_project = False
    correspondence_id: int | None = None

    with Session(engine) as db:
        project = db.query(Project).filter(Project.code == project_code).first()
        if not project:
            project = Project(code=project_code, name_e=f"Corr {project_code}", is_active=True)
            db.add(project)
            db.commit()
            created_project = True

        actor = SimpleNamespace(role="admin", id=None)
        create_payload = CorrespondenceCreateIn(
            project_code=project_code,
            issuing_code=project_code,
            category_code="CO",
            doc_type="Correspondence",
            direction="O",
            reference_no=f"{project_code}-CO-O-2602001",
            subject="Regression correspondence C2",
            sender="QA",
            recipient="PMO",
            status="Open",
            priority="High",
        )
        created = create_correspondence(payload=create_payload, db=db, user=actor)
        assert created.get("ok") is True
        item = created.get("data", {})
        correspondence_id = int(item["id"])
        assert item.get("project_code") == project_code
        assert item.get("issuing_code") == project_code
        assert item.get("category_code") == "CO"
        assert item.get("status") == "Open"

        listed = list_correspondence(issuing_code=project_code, skip=0, limit=50, db=db, user=actor)
        assert listed.get("ok") is True
        assert any(int(row.get("id")) == correspondence_id for row in listed.get("data", []))

        dashboard = get_correspondence_dashboard(db=db, user=actor)
        assert dashboard.get("ok") is True
        stats = dashboard.get("stats", {})
        assert int(stats.get("total", 0)) >= 1
        assert int(stats.get("open", 0)) >= 1

        update_payload = CorrespondenceUpdateIn(status="Closed", notes="Closed by regression test")
        updated = update_correspondence(
            correspondence_id=correspondence_id,
            payload=update_payload,
            db=db,
            user=actor,
        )
        assert updated.get("ok") is True
        assert updated.get("data", {}).get("status") == "Closed"

    with Session(engine) as db:
        if correspondence_id is not None:
            row = db.query(Correspondence).filter(Correspondence.id == correspondence_id).first()
            if row:
                db.delete(row)
        if created_project:
            project = db.query(Project).filter(Project.code == project_code).first()
            if project:
                db.delete(project)
        db.commit()


def test_regression_correspondence_c3_auto_reference_numbering() -> None:
    from types import SimpleNamespace

    from app.api.v1.routers.correspondence import CorrespondenceCreateIn, create_correspondence
    from app.db.models import Correspondence, Project

    project_code = f"CR{uuid.uuid4().hex[:6].upper()}"
    created_project = False
    created_ids: list[int] = []
    fixed_date = datetime(2026, 2, 6, 10, 30, 0)

    with Session(engine) as db:
        project = db.query(Project).filter(Project.code == project_code).first()
        if not project:
            project = Project(code=project_code, name_e=f"Corr Ref {project_code}", is_active=True)
            db.add(project)
            db.commit()
            created_project = True

        actor = SimpleNamespace(role="admin", id=None)
        payload = CorrespondenceCreateIn(
            project_code=project_code,
            issuing_code=project_code,
            category_code="CO",
            doc_type="Correspondence",
            direction="O",
            reference_no=None,
            subject="Auto reference test",
            corr_date=fixed_date,
            status="Open",
        )
        first = create_correspondence(payload=payload, db=db, user=actor)
        second = create_correspondence(payload=payload, db=db, user=actor)
        assert first.get("ok") is True
        assert second.get("ok") is True

        first_data = first.get("data", {})
        second_data = second.get("data", {})
        created_ids.extend([int(first_data["id"]), int(second_data["id"])])

        ref1 = str(first_data.get("reference_no") or "")
        ref2 = str(second_data.get("reference_no") or "")
        assert ref1 and ref2
        expected_prefix = f"{project_code}-CO-O-2602"
        assert ref1.startswith(expected_prefix)
        assert ref2.startswith(expected_prefix)
        assert re.match(rf"^{project_code}-CO-O-2602\d{{3}}$", ref1)
        assert re.match(rf"^{project_code}-CO-O-2602\d{{3}}$", ref2)

        serial1 = int(ref1[len(expected_prefix):])
        serial2 = int(ref2[len(expected_prefix):])
        assert serial2 == serial1 + 1
        assert len(ref1) == len(ref2)

    with Session(engine) as db:
        for corr_id in created_ids:
            row = db.query(Correspondence).filter(Correspondence.id == corr_id).first()
            if row:
                db.delete(row)
        if created_project:
            project = db.query(Project).filter(Project.code == project_code).first()
            if project:
                db.delete(project)
        db.commit()


def test_regression_correspondence_c5_actions_and_attachments_flow() -> None:
    from types import SimpleNamespace

    from fastapi import UploadFile

    from app.api.v1.routers.correspondence import (
        CorrespondenceCreateIn,
        CorrespondenceActionCreateIn,
        create_correspondence,
        create_correspondence_action,
        delete_correspondence_action,
        delete_correspondence_attachment,
        list_correspondence_actions,
        list_correspondence_attachments,
        update_correspondence_action,
        upload_correspondence_attachment,
    )
    from app.api.v1.routers.correspondence import CorrespondenceActionUpdateIn
    from app.db.models import Correspondence, Project

    project_code = f"CX{uuid.uuid4().hex[:6].upper()}"
    corr_id: int | None = None
    action_id: int | None = None
    attachment_id: int | None = None
    created_project = False

    with Session(engine) as db:
        project = db.query(Project).filter(Project.code == project_code).first()
        if not project:
            project = Project(code=project_code, name_e=f"C5 {project_code}", is_active=True)
            db.add(project)
            db.commit()
            created_project = True

        actor = SimpleNamespace(role="admin", id=None)
        created = create_correspondence(
            payload=CorrespondenceCreateIn(
                project_code=project_code,
                issuing_code=project_code,
                category_code="CO",
                doc_type="Correspondence",
                direction="O",
                reference_no=None,
                subject="C5 flow",
                status="Open",
            ),
            db=db,
            user=actor,
        )
        assert created.get("ok") is True
        corr_id = int(created.get("data", {}).get("id"))

        created_action = create_correspondence_action(
            correspondence_id=corr_id,
            payload=CorrespondenceActionCreateIn(
                action_type="task",
                title="Initial action",
                description="Action description",
                status="Open",
            ),
            db=db,
            user=actor,
        )
        assert created_action.get("ok") is True
        action_id = int(created_action.get("data", {}).get("id"))

        actions = list_correspondence_actions(correspondence_id=corr_id, db=db, user=actor)
        assert actions.get("ok") is True
        assert any(int(row.get("id")) == action_id for row in actions.get("data", []))

        updated = update_correspondence_action(
            action_id=action_id,
            payload=CorrespondenceActionUpdateIn(status="Closed", is_closed=True),
            db=db,
            user=actor,
        )
        assert updated.get("ok") is True
        assert updated.get("data", {}).get("is_closed") is True

        upload = upload_correspondence_attachment(
            correspondence_id=corr_id,
            file=UploadFile(filename="letter.txt", file=io.BytesIO(b"test-letter-content")),
            file_kind="letter",
            action_id=action_id,
            db=db,
            user=actor,
        )
        assert upload.get("ok") is True
        attachment = upload.get("data", {})
        attachment_id = int(attachment.get("id"))
        assert str(attachment.get("file_kind")) == "letter"

        attachments = list_correspondence_attachments(correspondence_id=corr_id, db=db, user=actor)
        assert attachments.get("ok") is True
        assert any(int(row.get("id")) == attachment_id for row in attachments.get("data", []))

        deleted_attachment = delete_correspondence_attachment(attachment_id=attachment_id, db=db, user=actor)
        assert deleted_attachment.get("ok") is True

        deleted_action = delete_correspondence_action(action_id=action_id, db=db, user=actor)
        assert deleted_action.get("ok") is True

    with Session(engine) as db:
        if corr_id is not None:
            row = db.query(Correspondence).filter(Correspondence.id == corr_id).first()
            if row:
                db.delete(row)
        if created_project:
            project = db.query(Project).filter(Project.code == project_code).first()
            if project:
                db.delete(project)
        db.commit()


def test_regression_archive_dual_upload_links_files(admin_headers: dict[str, str]) -> None:
    from app.db.models import ArchiveFile, DocumentRevision, MdrDocument, Project

    project_code = f"TD{uuid.uuid4().hex[:6].upper()}"
    doc_number = f"{project_code}-EGN0001-TGEN"

    created_project = False
    created_doc = False
    pdf_path: str | None = None
    native_path: str | None = None
    pdf_file_id: int | None = None
    native_file_id: int | None = None
    doc_id: int | None = None

    with Session(engine) as db:
        project = db.query(Project).filter(Project.code == project_code).first()
        if not project:
            project = Project(code=project_code, name_e=f"Dual Test {project_code}", is_active=True)
            db.add(project)
            created_project = True

        doc = db.query(MdrDocument).filter(MdrDocument.doc_number == doc_number).first()
        if not doc:
            doc = MdrDocument(
                doc_number=doc_number,
                doc_title_e=f"Dual Upload {project_code}",
                subject=f"Dual Upload {project_code}",
                project_code=project_code,
                mdr_code="E",
                discipline_code=None,
                package_code=None,
                block="T",
                level_code=None,
            )
            db.add(doc)
            created_doc = True

        db.commit()
        db.refresh(doc)
        doc_id = doc.id

    files = {
        "pdf_file": ("dual-test.pdf", io.BytesIO(b"%PDF-dual-test%"), "application/pdf"),
        "native_file": ("dual-test.dwg", io.BytesIO(b"dual-native-content"), "application/octet-stream"),
    }
    payload = {"document_id": str(doc_id), "revision": "D1", "status": "IFA"}
    response = client.post("/api/v1/archive/upload-dual", data=payload, files=files, headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True

    pdf_file_id = body.get("pdf_file_id")
    native_file_id = body.get("native_file_id")
    assert isinstance(pdf_file_id, int)
    assert isinstance(native_file_id, int)

    with Session(engine) as db:
        pdf_row = db.query(ArchiveFile).filter(ArchiveFile.id == pdf_file_id).first()
        native_row = db.query(ArchiveFile).filter(ArchiveFile.id == native_file_id).first()
        assert pdf_row is not None
        assert native_row is not None
        assert pdf_row.file_kind == "pdf"
        assert native_row.file_kind == "native"
        assert bool(pdf_row.is_primary) is True
        assert bool(native_row.is_primary) is False
        assert pdf_row.companion_file_id == native_row.id
        assert native_row.companion_file_id == pdf_row.id
        assert pdf_row.revision_id == native_row.revision_id
        pdf_path = pdf_row.stored_path
        native_path = native_row.stored_path

        revision_row = db.query(DocumentRevision).filter(DocumentRevision.id == pdf_row.revision_id).first()
        assert revision_row is not None
        assert revision_row.file_path == pdf_row.stored_path

    list_res = client.get("/api/v1/archive/list?limit=200", headers=admin_headers)
    if list_res.status_code == 429:
        pytest.skip("Rate limit middleware reached during archive list verification")
    assert list_res.status_code == 200, list_res.text
    list_body = list_res.json()
    assert list_body.get("ok") is True
    rows = list_body.get("data", [])
    row_for_doc = next((r for r in rows if r.get("document_id") == doc_id), None)
    assert row_for_doc is not None
    assert row_for_doc.get("project_code") == project_code
    assert "discipline_code" in row_for_doc
    assert isinstance(row_for_doc.get("pdf_file_id"), int)
    assert isinstance(row_for_doc.get("native_file_id"), int)
    assert row_for_doc.get("pdf_file_id") in (pdf_file_id, native_file_id)
    assert row_for_doc.get("native_file_id") in (pdf_file_id, native_file_id)
    assert row_for_doc.get("pdf_file_id") != row_for_doc.get("native_file_id")

    filtered_res = client.get(
        f"/api/v1/archive/list?project_code={project_code}&status=IFA&date_from=2000-01-01&date_to=2100-01-01&limit=200",
        headers=admin_headers,
    )
    if filtered_res.status_code == 429:
        pytest.skip("Rate limit middleware reached during archive filters verification")
    assert filtered_res.status_code == 200, filtered_res.text
    filtered_rows = filtered_res.json().get("data", [])
    filtered_for_doc = next((r for r in filtered_rows if r.get("document_id") == doc_id), None)
    assert filtered_for_doc is not None

    history_res = client.get(f"/api/v1/archive/revision-history/{doc_id}", headers=admin_headers)
    if history_res.status_code == 429:
        pytest.skip("Rate limit middleware reached during revision history verification")
    assert history_res.status_code == 200, history_res.text
    history = history_res.json()
    assert history.get("ok") is True
    assert history.get("document", {}).get("id") == doc_id
    revisions = history.get("revisions", [])
    assert isinstance(revisions, list)
    matching_rev = next((rev for rev in revisions if rev.get("revision") == "D1"), None)
    assert matching_rev is not None
    files = matching_rev.get("files", [])
    assert isinstance(files, list)
    kinds = {f.get("file_kind") for f in files}
    assert "pdf" in kinds
    assert "native" in kinds
    returned_ids = {int(f.get("id")) for f in files if f.get("id") is not None}
    assert pdf_file_id in returned_ids
    assert native_file_id in returned_ids

    # cleanup
    with Session(engine) as db:
        if pdf_file_id is not None:
            row = db.query(ArchiveFile).filter(ArchiveFile.id == pdf_file_id).first()
            if row:
                db.delete(row)
        if native_file_id is not None:
            row = db.query(ArchiveFile).filter(ArchiveFile.id == native_file_id).first()
            if row:
                db.delete(row)

        if doc_id is not None:
            revs = db.query(DocumentRevision).filter(DocumentRevision.document_id == doc_id).all()
            for rev in revs:
                db.delete(rev)
            doc = db.query(MdrDocument).filter(MdrDocument.id == doc_id).first()
            if doc and created_doc:
                db.delete(doc)

        if created_project:
            project = db.query(Project).filter(Project.code == project_code).first()
            if project:
                db.delete(project)
        db.commit()

    for path in (pdf_path, native_path):
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


def test_regression_permissions_scope_roundtrip(admin_headers: dict[str, str]) -> None:
    """
    Permissions scope should be configurable per role with project/discipline lists.
    """
    get_res = client.get("/api/v1/settings/permissions/scope", headers=admin_headers)
    assert get_res.status_code == 200, get_res.text
    payload = get_res.json()
    assert payload.get("ok") is True

    roles = payload.get("roles", [])
    scope = payload.get("scope", {})
    assert "user" in roles
    assert isinstance(scope.get("user", {}), dict)

    projects = payload.get("projects", [])
    disciplines = payload.get("disciplines", [])
    project_code = projects[0]["code"] if projects else None
    discipline_code = disciplines[0]["code"] if disciplines else None

    user_scope = {
        "projects": [project_code] if project_code else [],
        "disciplines": [discipline_code] if discipline_code else [],
    }
    scope["user"] = user_scope

    save_res = client.post(
        "/api/v1/settings/permissions/scope",
        json={"scope": scope},
        headers=admin_headers,
    )
    assert save_res.status_code == 200, save_res.text
    saved = save_res.json()
    assert saved.get("ok") is True
    assert saved.get("scope", {}).get("user", {}).get("projects", []) == user_scope["projects"]
    assert saved.get("scope", {}).get("user", {}).get("disciplines", []) == user_scope["disciplines"]


def test_regression_user_permissions_scope_roundtrip(admin_headers: dict[str, str]) -> None:
    """
    User-specific scope should be configurable per user.
    """
    users_res = client.get("/api/v1/users/", headers=admin_headers)
    assert users_res.status_code == 200, users_res.text
    users = users_res.json()
    target_user = next((u for u in users if u.get("role") != "admin"), None)
    if not target_user:
        pytest.skip("No non-admin user found for user scope regression test")

    scope_res = client.get("/api/v1/settings/permissions/scope", headers=admin_headers)
    assert scope_res.status_code == 200, scope_res.text
    scope_body = scope_res.json()
    projects = scope_body.get("projects", [])
    disciplines = scope_body.get("disciplines", [])
    project_code = projects[0]["code"] if projects else None
    discipline_code = disciplines[0]["code"] if disciplines else None

    payload = {
        "user_id": target_user["id"],
        "projects": [project_code] if project_code else [],
        "disciplines": [discipline_code] if discipline_code else [],
    }
    save_res = client.post(
        "/api/v1/settings/permissions/user-scope/upsert",
        json=payload,
        headers=admin_headers,
    )
    assert save_res.status_code == 200, save_res.text
    saved = save_res.json()
    assert saved.get("ok") is True
    assert saved.get("scope", {}).get("projects", []) == payload["projects"]
    assert saved.get("scope", {}).get("disciplines", []) == payload["disciplines"]

    get_user_scope_res = client.get("/api/v1/settings/permissions/user-scope", headers=admin_headers)
    assert get_user_scope_res.status_code == 200, get_user_scope_res.text
    all_scope = get_user_scope_res.json().get("scope", {})
    user_scope = all_scope.get(str(target_user["id"]), {})
    assert user_scope.get("projects", []) == payload["projects"]
    assert user_scope.get("disciplines", []) == payload["disciplines"]


def test_regression_permissions_access_report_and_audit(admin_headers: dict[str, str]) -> None:
    scope_res = client.get("/api/v1/settings/permissions/scope", headers=admin_headers)
    assert scope_res.status_code == 200, scope_res.text
    scope_body = scope_res.json()
    projects = scope_body.get("projects", [])
    if not projects:
        pytest.skip("No projects found for access report test")
    project_code = projects[0]["code"]

    report_res = client.get(
        f"/api/v1/settings/permissions/access-report?project_code={project_code}",
        headers=admin_headers,
    )
    assert report_res.status_code == 200, report_res.text
    report_body = report_res.json()
    assert report_body.get("ok") is True
    assert isinstance(report_body.get("items"), list)
    assert all(bool(item.get("has_access")) for item in report_body.get("items", []))

    # Trigger an audited permission-settings change (idempotent save).
    save_res = client.post(
        "/api/v1/settings/permissions/scope",
        json={"scope": scope_body.get("scope", {})},
        headers=admin_headers,
    )
    assert save_res.status_code == 200, save_res.text

    logs_res = client.get(
        "/api/v1/settings/permissions/audit-logs?action=permissions.scope.save&limit=5",
        headers=admin_headers,
    )
    assert logs_res.status_code == 200, logs_res.text
    logs_body = logs_res.json()
    assert logs_body.get("ok") is True
    items = logs_body.get("items", [])
    assert isinstance(items, list)
    assert any(i.get("action") == "permissions.scope.save" for i in items), logs_body


def test_regression_permissions_access_report_csv_and_user_access(admin_headers: dict[str, str]) -> None:
    scope_res = client.get("/api/v1/settings/permissions/scope", headers=admin_headers)
    assert scope_res.status_code == 200, scope_res.text
    scope_body = scope_res.json()
    projects = scope_body.get("projects", [])
    if not projects:
        pytest.skip("No projects found for access report csv test")
    project_code = projects[0]["code"]

    csv_res = client.get(
        f"/api/v1/settings/permissions/access-report.csv?project_code={project_code}",
        headers=admin_headers,
    )
    assert csv_res.status_code == 200, csv_res.text
    assert "text/csv" in (csv_res.headers.get("content-type") or "")
    csv_body = csv_res.text
    assert "user_id,email,full_name,role" in csv_body
    assert f",{project_code}," in csv_body or csv_body.endswith(project_code)

    users_res = client.get("/api/v1/users/", headers=admin_headers)
    assert users_res.status_code == 200, users_res.text
    users = users_res.json()
    if not users:
        pytest.skip("No users found for user access report test")

    target_user = next((u for u in users if u.get("role") != "admin"), users[0])
    user_access_res = client.get(
        f"/api/v1/settings/permissions/user-access/{target_user['id']}",
        headers=admin_headers,
    )
    assert user_access_res.status_code == 200, user_access_res.text
    body = user_access_res.json()
    assert body.get("ok") is True
    assert body.get("user", {}).get("id") == target_user["id"]
    assert "effective_scope" in body
    assert "projects" in body.get("effective_scope", {})
    assert "disciplines" in body.get("effective_scope", {})
    assert "effective_scope_catalog" in body


def test_regression_settings_master_data_audit_log(admin_headers: dict[str, str]) -> None:
    code = f"LVREG{uuid.uuid4().hex[:6].upper()}"
    upsert_res = client.post(
        "/api/v1/settings/levels/upsert",
        json={
            "code": code,
            "name_e": f"Regression {code}",
            "name_p": "",
            "sort_order": 9999,
        },
        headers=admin_headers,
    )
    assert upsert_res.status_code == 200, upsert_res.text
    upsert_body = upsert_res.json()
    assert upsert_body.get("ok") is True

    audit_res = client.get(
        f"/api/v1/settings/audit-logs?action=level.upsert&target_type=level&target_key={code}",
        headers=admin_headers,
    )
    assert audit_res.status_code == 200, audit_res.text
    audit_body = audit_res.json()
    assert audit_body.get("ok") is True
    items = audit_body.get("items", [])
    assert any(i.get("action") == "level.upsert" and i.get("target_key") == code for i in items), audit_body

    cleanup_res = client.post(
        "/api/v1/settings/levels/delete",
        json={"code": code},
        headers=admin_headers,
    )
    assert cleanup_res.status_code in (200, 409), cleanup_res.text


def test_regression_settings_audit_server_pagination(admin_headers: dict[str, str]) -> None:
    page1_res = client.get(
        "/api/v1/settings/audit-logs?action=permissions.scope.save&page=1&page_size=1",
        headers=admin_headers,
    )
    if page1_res.status_code == 429:
        pytest.skip("Rate limit middleware reached during pagination test")
    if page1_res.status_code != 200:
        scope_res = client.get("/api/v1/settings/permissions/scope", headers=admin_headers)
        assert scope_res.status_code == 200, scope_res.text
        save_res = client.post(
            "/api/v1/settings/permissions/scope",
            json={"scope": scope_res.json().get("scope", {})},
            headers=admin_headers,
        )
        assert save_res.status_code == 200, save_res.text
        page1_res = client.get(
            "/api/v1/settings/audit-logs?action=permissions.scope.save&page=1&page_size=1",
            headers=admin_headers,
        )
    assert page1_res.status_code == 200, page1_res.text
    page1_body = page1_res.json()
    assert page1_body.get("ok") is True

    pagination = page1_body.get("pagination", {})
    items1 = page1_body.get("items", [])
    assert pagination.get("page") == 1
    assert pagination.get("page_size") == 1
    assert isinstance(items1, list)
    assert pagination.get("count") == len(items1)
    assert int(pagination.get("total", 0)) >= len(items1)
    assert int(pagination.get("total_pages", 1)) >= 1

    total_rows = int(pagination.get("total", 0))
    if total_rows > 1:
        page2_res = client.get(
            "/api/v1/settings/audit-logs?action=permissions.scope.save&page=2&page_size=1",
            headers=admin_headers,
        )
        assert page2_res.status_code == 200, page2_res.text
        page2_body = page2_res.json()
        assert page2_body.get("ok") is True
        pagination2 = page2_body.get("pagination", {})
        items2 = page2_body.get("items", [])
        assert pagination2.get("page") == 2
        assert pagination2.get("page_size") == 1
        assert pagination2.get("count") == len(items2)
        if items1 and items2:
            assert items1[0].get("id") != items2[0].get("id")

    offset_value = 1 if total_rows > 1 else 0
    offset_res = client.get(
        f"/api/v1/settings/audit-logs?action=permissions.scope.save&offset={offset_value}&page_size=1",
        headers=admin_headers,
    )
    assert offset_res.status_code == 200, offset_res.text
    offset_body = offset_res.json()
    assert offset_body.get("ok") is True
    offset_pagination = offset_body.get("pagination", {})
    assert offset_pagination.get("offset") == offset_value
    assert offset_pagination.get("page_size") == 1
    assert offset_pagination.get("count") == len(offset_body.get("items", []))


def test_regression_bulk_empty_subject_does_not_fallback_to_title(admin_headers: dict[str, str]) -> None:
    """
    Subject is optional in bulk rows.
    If subject is empty, frontend must not replace it with title_p/title_e.
    """
    project_code = f"T{uuid.uuid4().hex[:5].upper()}"
    title_fallback = f"Fallback-{uuid.uuid4().hex[:6]}"

    line1 = "\t".join(
        [
            project_code,  # project
            "E",           # mdr
            "X",           # phase
            "GN",          # disc
            "00",          # pkg
            "G",           # block
            "GEN",         # level
            "",            # subject (intentionally empty)
            title_fallback,
            "",
            "",            # doc code (let backend generate)
        ]
    )
    line2 = "\t".join(
        [
            project_code,  # same prefix
            "E",
            "X",
            "GN",
            "00",
            "G",
            "GEN",
            "",            # subject still empty
            title_fallback,  # same title to catch fallback bug
            "",
            "",
        ]
    )

    response = client.post(
        "/api/v1/mdr/bulk-register",
        headers={**admin_headers, "Content-Type": "application/json"},
        json={"text_data": f"{line1}\n{line2}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True, body
    assert body.get("stats", {}).get("success") == 2, body

    details = body.get("stats", {}).get("details", [])
    doc_numbers = [d.get("doc_number", "") for d in details if d.get("status") == "Success"]
    assert len(doc_numbers) == 2, body
    assert doc_numbers[0] != doc_numbers[1], body

    with Session(engine) as db:
        rows = (
            db.query(MdrDocument)
            .filter(
                MdrDocument.project_code == project_code,
                MdrDocument.doc_number.in_(doc_numbers),
            )
            .all()
        )
    assert len(rows) == 2
    assert all((r.subject or "") == "" for r in rows)
