from __future__ import annotations

import uuid
import io
import os
import re
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.main import app
from app.db.models import Level, MdrDocument, Package
from app.db.session import engine
from app.services import docnum_service, mdr_service
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
    assert users, "Expected at least one user from deterministic seed."

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
    assert projects, "Expected at least one project from deterministic seed."
    project = projects[0]
    assert any(key in project for key in ("project_name", "name", "name_e"))


def test_regression_auth_navigation_edms_tabs(admin_headers: dict[str, str]) -> None:
    res = client.get("/api/v1/auth/navigation", headers=admin_headers)
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
    original_allowed_roots = settings.STORAGE_ALLOWED_ROOTS
    original_require_absolute = settings.STORAGE_REQUIRE_ABSOLUTE_PATHS
    original_validate_writable = settings.STORAGE_VALIDATE_WRITABLE_ON_SAVE
    tmp_root = (Path(settings.BASE_DIR) / "database" / f"reg_storage_{uuid.uuid4().hex[:6]}").resolve()
    tmp_root.mkdir(parents=True, exist_ok=True)
    settings.STORAGE_ALLOWED_ROOTS = str(tmp_root)
    settings.STORAGE_REQUIRE_ABSOLUTE_PATHS = True
    settings.STORAGE_VALIDATE_WRITABLE_ON_SAVE = True

    get_res = client.get("/api/v1/settings/storage-paths", headers=admin_headers)
    assert get_res.status_code == 200, get_res.text
    before = get_res.json()
    assert before.get("ok") is True

    payload = {
        "mdr_storage_path": str((tmp_root / f"technical_{uuid.uuid4().hex[:6]}").resolve()),
        "correspondence_storage_path": str(
            (tmp_root / f"correspondence_{uuid.uuid4().hex[:6]}").resolve()
        ),
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
        settings.STORAGE_REQUIRE_ABSOLUTE_PATHS = False
        settings.STORAGE_VALIDATE_WRITABLE_ON_SAVE = False
        settings.STORAGE_ALLOWED_ROOTS = ""
        restore_payload = {
            "mdr_storage_path": before.get("mdr_storage_path") or "./files/technical",
            "correspondence_storage_path": before.get("correspondence_storage_path") or "./files/correspondence",
            "site_log_storage_path": before.get("site_log_storage_path") or "",
        }
        restore_res = client.post(
            "/api/v1/settings/storage-paths",
            json=restore_payload,
            headers=admin_headers,
        )
        assert restore_res.status_code == 200, restore_res.text
        settings.STORAGE_ALLOWED_ROOTS = original_allowed_roots
        settings.STORAGE_REQUIRE_ABSOLUTE_PATHS = original_require_absolute
        settings.STORAGE_VALIDATE_WRITABLE_ON_SAVE = original_validate_writable


def test_regression_archive_files_dual_file_columns_exist() -> None:
    inspector = inspect(engine)
    assert inspector.has_table("archive_files"), "archive_files table must exist after init/migrations."
    column_names = {str(col["name"]) for col in inspector.get_columns("archive_files")}

    assert "file_kind" in column_names
    assert "is_primary" in column_names
    assert "companion_file_id" in column_names


def test_regression_correspondence_tables_exist() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    required_tables = {
        "correspondences",
        "correspondence_actions",
        "correspondence_attachments",
        "correspondence_tag_assignments",
        "document_tags",
        "issuing_entities",
        "correspondence_categories",
        "correspondence_departments",
    }
    if not required_tables.issubset(table_names):
        from app.db.session import init_db

        init_db()
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())

    assert required_tables.issubset(table_names)

    corr_columns = {str(col["name"]) for col in inspector.get_columns("correspondences")}
    action_columns = {str(col["name"]) for col in inspector.get_columns("correspondence_actions")}
    attachment_columns = {
        str(col["name"]) for col in inspector.get_columns("correspondence_attachments")
    }
    tag_assignment_columns = {
        str(col["name"]) for col in inspector.get_columns("correspondence_tag_assignments")
    }
    tag_columns = {str(col["name"]) for col in inspector.get_columns("document_tags")}
    corr_indexes = {str(idx["name"]): bool(idx.get("unique", False)) for idx in inspector.get_indexes("correspondences")}
    corr_uniques = {
        str(item.get("name"))
        for item in inspector.get_unique_constraints("correspondences")
        if item.get("name")
    }
    tag_assignment_indexes = {
        str(idx["name"]): bool(idx.get("unique", False))
        for idx in inspector.get_indexes("correspondence_tag_assignments")
    }
    tag_assignment_uniques = {
        str(item.get("name"))
        for item in inspector.get_unique_constraints("correspondence_tag_assignments")
        if item.get("name")
    }

    for required in (
        "project_code",
        "issuing_code",
        "category_code",
        "department_code",
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
    for required in (
        "correspondence_id",
        "tag_id",
        "assigned_by_id",
        "assigned_at",
    ):
        assert required in tag_assignment_columns
    for required in ("id", "scope", "name", "color", "created_at"):
        assert required in tag_columns
    assert (
        "uq_correspondences_reference_no" in corr_indexes
        or "uq_correspondences_reference_no" in corr_uniques
    )
    if "uq_correspondences_reference_no" in corr_indexes:
        assert corr_indexes["uq_correspondences_reference_no"] is True
    assert (
        "uq_corr_tag_assignment" in tag_assignment_indexes
        or "uq_corr_tag_assignment" in tag_assignment_uniques
    )


def test_regression_correspondence_tags_settings_and_runtime_flow(
    admin_headers: dict[str, str],
) -> None:
    from app.db.models import Correspondence, CorrespondenceDepartment, CorrespondenceTagAssignment, DocumentTag, Project

    project_code = f"CT{uuid.uuid4().hex[:6].upper()}"
    reference_no = f"{project_code}-CO-O-{uuid.uuid4().hex[:7].upper()}"
    subject = f"Regression tag flow {uuid.uuid4().hex[:6]}"
    tag_name = f"Regression Tag {uuid.uuid4().hex[:6]}"
    next_tag_name = f"Regression Tag {uuid.uuid4().hex[:6]}"
    department_code = f"DEP{uuid.uuid4().hex[:5].upper()}"
    next_department_code = f"DEP{uuid.uuid4().hex[:5].upper()}"
    document_tag_name = f"Regression Document Tag {uuid.uuid4().hex[:6]}"
    correspondence_id: int | None = None
    tag_ids: list[int] = []
    document_tag_ids: list[int] = []
    department_codes: list[str] = []

    with Session(engine) as db:
        project = db.query(Project).filter(Project.code == project_code).first()
        if not project:
            db.add(Project(code=project_code, name_e=f"Project {project_code}", is_active=True))
            db.commit()

    try:
        create_tag = client.post(
            "/api/v1/settings/correspondence-tags/upsert",
            json={"name": tag_name, "color": "#22AA88"},
            headers=admin_headers,
        )
        assert create_tag.status_code == 200, create_tag.text
        first_tag_id = int(create_tag.json().get("id") or 0)
        assert first_tag_id > 0
        tag_ids.append(first_tag_id)

        create_next_tag = client.post(
            "/api/v1/settings/correspondence-tags/upsert",
            json={"name": next_tag_name, "color": "#2563EB"},
            headers=admin_headers,
        )
        assert create_next_tag.status_code == 200, create_next_tag.text
        second_tag_id = int(create_next_tag.json().get("id") or 0)
        assert second_tag_id > 0
        tag_ids.append(second_tag_id)

        create_document_tag = client.post(
            "/api/v1/settings/document-tags/upsert",
            json={"name": document_tag_name, "color": "#7C3AED"},
            headers=admin_headers,
        )
        assert create_document_tag.status_code == 200, create_document_tag.text
        document_tag_id = int(create_document_tag.json().get("id") or 0)
        assert document_tag_id > 0
        document_tag_ids.append(document_tag_id)

        for code, name in (
            (department_code, "Regression Design Department"),
            (next_department_code, "Regression Finance Department"),
        ):
            create_department = client.post(
                "/api/v1/settings/correspondence-departments/upsert",
                json={"code": code, "name_e": name, "name_p": name, "is_active": True},
                headers=admin_headers,
            )
            assert create_department.status_code == 200, create_department.text
            department_codes.append(code)

        settings_departments = client.get("/api/v1/settings/correspondence-departments", headers=admin_headers)
        assert settings_departments.status_code == 200, settings_departments.text
        settings_department_items = settings_departments.json().get("items") or []
        assert any(item.get("code") == department_code for item in settings_department_items)
        assert any(item.get("code") == next_department_code for item in settings_department_items)

        settings_tags = client.get("/api/v1/settings/correspondence-tags", headers=admin_headers)
        assert settings_tags.status_code == 200, settings_tags.text
        settings_items = settings_tags.json().get("items") or []
        assert any(int(item.get("id") or 0) == first_tag_id for item in settings_items)
        assert any(int(item.get("id") or 0) == second_tag_id for item in settings_items)
        assert all(int(item.get("id") or 0) != document_tag_id for item in settings_items)

        document_tags = client.get("/api/v1/settings/document-tags", headers=admin_headers)
        assert document_tags.status_code == 200, document_tags.text
        document_tag_items = document_tags.json().get("items") or []
        assert any(int(item.get("id") or 0) == document_tag_id for item in document_tag_items)
        assert all(int(item.get("id") or 0) != first_tag_id for item in document_tag_items)

        catalog_res = client.get("/api/v1/correspondence/catalog", headers=admin_headers)
        assert catalog_res.status_code == 200, catalog_res.text
        catalog_tags = catalog_res.json().get("tags") or []
        catalog_departments = catalog_res.json().get("departments") or []
        assert any(int(item.get("id") or 0) == first_tag_id for item in catalog_tags)
        assert any(int(item.get("id") or 0) == second_tag_id for item in catalog_tags)
        assert all(int(item.get("id") or 0) != document_tag_id for item in catalog_tags)
        assert any(item.get("code") == department_code for item in catalog_departments)
        assert any(item.get("code") == next_department_code for item in catalog_departments)

        archive_tags = client.get("/api/v1/archive/tags", headers=admin_headers)
        assert archive_tags.status_code == 200, archive_tags.text
        archive_tag_items = archive_tags.json().get("items") or []
        assert any(int(item.get("id") or 0) == document_tag_id for item in archive_tag_items)
        assert all(int(item.get("id") or 0) != first_tag_id for item in archive_tag_items)

        create_corr = client.post(
            "/api/v1/correspondence/create",
            json={
                "project_code": project_code,
                "issuing_code": project_code,
                "category_code": "CO",
                "department_code": department_code,
                "doc_type": "Correspondence",
                "direction": "O",
                "reference_no": reference_no,
                "subject": subject,
                "sender": "QA",
                "recipient": "PMO",
                "status": "Open",
                "priority": "Normal",
                "tag_id": first_tag_id,
            },
            headers=admin_headers,
        )
        assert create_corr.status_code == 200, create_corr.text
        created_item = (create_corr.json().get("data") or {})
        correspondence_id = int(created_item.get("id") or 0)
        assert correspondence_id > 0
        assert created_item.get("department_code") == department_code
        assert int(created_item.get("tag_id") or 0) == first_tag_id
        assert first_tag_id in [int(value) for value in (created_item.get("tag_ids") or [])]

        update_corr = client.put(
            f"/api/v1/correspondence/{correspondence_id}",
            json={"department_code": next_department_code, "tag_id": second_tag_id, "status": "Closed"},
            headers=admin_headers,
        )
        assert update_corr.status_code == 200, update_corr.text
        updated_item = (update_corr.json().get("data") or {})
        assert updated_item.get("status") == "Closed"
        assert updated_item.get("department_code") == next_department_code
        assert int(updated_item.get("tag_id") or 0) == second_tag_id
        assert [int(value) for value in (updated_item.get("tag_ids") or [])] == [second_tag_id]

        list_res = client.get(
            f"/api/v1/correspondence/list?project_code={project_code}&department_code={next_department_code}&tag_id={second_tag_id}",
            headers=admin_headers,
        )
        assert list_res.status_code == 200, list_res.text
        listed_items = list_res.json().get("data") or []
        matched = next(
            (item for item in listed_items if int(item.get("id") or 0) == correspondence_id),
            None,
        )
        assert matched is not None
        assert matched.get("department_code") == next_department_code
        assert int(matched.get("tag_id") or 0) == second_tag_id
    finally:
        with Session(engine) as db:
            if correspondence_id is not None:
                db.query(CorrespondenceTagAssignment).filter(
                    CorrespondenceTagAssignment.correspondence_id == correspondence_id
                ).delete(synchronize_session=False)
                db.query(Correspondence).filter(Correspondence.id == correspondence_id).delete(
                    synchronize_session=False
                )
            if tag_ids:
                db.query(DocumentTag).filter(DocumentTag.id.in_(tag_ids)).delete(
                    synchronize_session=False
                )
            if document_tag_ids:
                db.query(DocumentTag).filter(DocumentTag.id.in_(document_tag_ids)).delete(
                    synchronize_session=False
                )
            if department_codes:
                db.query(CorrespondenceDepartment).filter(
                    CorrespondenceDepartment.code.in_(department_codes)
                ).delete(synchronize_session=False)
            db.query(Project).filter(Project.code == project_code).delete(
                synchronize_session=False
            )
            db.commit()


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
    from app.db.models import Correspondence, CorrespondenceAttachment, Project

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
    from app.db.models import Correspondence, CorrespondenceAttachment, Project

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
    from app.db.models import Correspondence, CorrespondenceAttachment, Project

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
        attachment_row = (
            db.query(CorrespondenceAttachment)
            .filter(CorrespondenceAttachment.id == attachment_id)
            .first()
        )
        corr_row = db.query(Correspondence).filter(Correspondence.id == corr_id).first()
        assert attachment_row is not None
        assert corr_row is not None
        stored_path = Path(str(attachment_row.stored_path))
        assert stored_path.parent.name == "main"
        assert stored_path.parent.parent.name == corr_row.reference_no
        assert stored_path.parent.parent.parent.name == "O"
        assert stored_path.name.startswith(f"{corr_row.reference_no}_")

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
        pdf_path_obj = Path(str(pdf_path))
        native_path_obj = Path(str(native_path))
        assert pdf_path_obj.parent.name == "pdf"
        assert native_path_obj.parent.name == "native"
        assert f"{project_code} - Dual Test {project_code}" in pdf_path_obj.parts
        assert f"{project_code} - Dual Test {project_code}" in native_path_obj.parts
        assert "GN" in pdf_path_obj.parts
        assert "GN" in native_path_obj.parts

        revision_row = db.query(DocumentRevision).filter(DocumentRevision.id == pdf_row.revision_id).first()
        assert revision_row is not None
        assert revision_row.file_path == pdf_row.stored_path

    list_res = client.get("/api/v1/archive/list?limit=200", headers=admin_headers)
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
    assert filtered_res.status_code == 200, filtered_res.text
    filtered_rows = filtered_res.json().get("data", [])
    filtered_for_doc = next((r for r in filtered_rows if r.get("document_id") == doc_id), None)
    assert filtered_for_doc is not None

    history_res = client.get(f"/api/v1/archive/revision-history/{doc_id}", headers=admin_headers)
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
        rows_to_delete = []
        if pdf_file_id is not None:
            row = db.query(ArchiveFile).filter(ArchiveFile.id == pdf_file_id).first()
            if row:
                rows_to_delete.append(row)
        if native_file_id is not None:
            row = db.query(ArchiveFile).filter(ArchiveFile.id == native_file_id).first()
            if row:
                rows_to_delete.append(row)

        # Break self-reference link before delete (required by PostgreSQL FK checks).
        for row in rows_to_delete:
            row.companion_file_id = None
        if rows_to_delete:
            db.flush()
            for row in rows_to_delete:
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


def test_regression_archive_native_only_upload_is_listed(admin_headers: dict[str, str]) -> None:
    from app.db.models import ArchiveFile, DocumentRevision, MdrDocument, Project

    project_code = f"TN{uuid.uuid4().hex[:6].upper()}"
    doc_number = f"{project_code}-EGN0001-TGEN"

    created_project = False
    native_path: str | None = None
    native_file_id: int | None = None
    doc_id: int | None = None

    with Session(engine) as db:
        project = db.query(Project).filter(Project.code == project_code).first()
        if not project:
            project = Project(code=project_code, name_e=f"Native Only {project_code}", is_active=True)
            db.add(project)
            created_project = True

        doc = MdrDocument(
            doc_number=doc_number,
            doc_title_e=f"Native Only Upload {project_code}",
            subject=f"Native Only Upload {project_code}",
            project_code=project_code,
            mdr_code="E",
            discipline_code=None,
            package_code=None,
            block="T",
            level_code=None,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id

    files = {"file": ("native-only.dwg", io.BytesIO(b"native-only-content"), "application/octet-stream")}
    payload = {"document_id": str(doc_id), "revision": "N1", "status": "IFA", "file_kind": "native"}
    response = client.post("/api/v1/archive/upload", data=payload, files=files, headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True
    native_file_id = body.get("file_id")
    assert isinstance(native_file_id, int)

    with Session(engine) as db:
        native_row = db.query(ArchiveFile).filter(ArchiveFile.id == native_file_id).first()
        assert native_row is not None
        assert native_row.file_kind == "native"
        assert bool(native_row.is_primary) is True
        native_path = native_row.stored_path

    list_res = client.get(f"/api/v1/archive/list?project_code={project_code}&limit=200", headers=admin_headers)
    assert list_res.status_code == 200, list_res.text
    rows = list_res.json().get("data", [])
    row_for_doc = next((r for r in rows if r.get("document_id") == doc_id), None)
    assert row_for_doc is not None
    assert row_for_doc.get("file_kind") == "native"
    assert row_for_doc.get("pdf_file_id") is None
    assert row_for_doc.get("native_file_id") == native_file_id
    assert row_for_doc.get("native_file_name")

    with Session(engine) as db:
        if native_file_id is not None:
            row = db.query(ArchiveFile).filter(ArchiveFile.id == native_file_id).first()
            if row:
                db.delete(row)

        if doc_id is not None:
            revs = db.query(DocumentRevision).filter(DocumentRevision.document_id == doc_id).all()
            for rev in revs:
                db.delete(rev)
            doc = db.query(MdrDocument).filter(MdrDocument.id == doc_id).first()
            if doc:
                db.delete(doc)

        if created_project:
            project = db.query(Project).filter(Project.code == project_code).first()
            if project:
                db.delete(project)
        db.commit()

    if native_path and os.path.exists(native_path):
        try:
            os.remove(native_path)
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
    assert target_user is not None, "Expected at least one non-admin user from deterministic seed."

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
    assert projects, "Expected at least one project from deterministic seed."
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
    assert projects, "Expected at least one project from deterministic seed."
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
    assert users, "Expected at least one user from deterministic seed."

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


def test_regression_bulk_empty_subject_uses_single_subjectless_doc_with_one_serial(
    admin_headers: dict[str, str],
) -> None:
    """
    Subject is optional in bulk rows.
    For the same scope, subjectless rows must reuse the single `01` document.
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
    stats = body.get("stats", {})
    assert stats.get("success") == 1, body
    assert stats.get("failed") == 0, body

    details = stats.get("details", [])
    success_rows = [d for d in details if str(d.get("status", "")).lower() == "success"]
    skipped_rows = [d for d in details if str(d.get("status", "")).lower() == "skipped"]
    assert len(success_rows) == 1, body
    assert len(skipped_rows) == 1, body
    success_doc = str(success_rows[0].get("doc_number") or "").strip().upper()
    skipped_doc = str(skipped_rows[0].get("doc_number") or "").strip().upper()
    assert success_doc
    assert skipped_doc == success_doc

    with Session(engine) as db:
        rows = (
            db.query(MdrDocument)
            .filter(
                MdrDocument.project_code == project_code,
                MdrDocument.doc_number == success_doc,
            )
            .all()
        )
    assert len(rows) == 1
    assert all((r.subject or "") == "" for r in rows)


def test_regression_bulk_subjectless_explicit_non_one_serial_fails(admin_headers: dict[str, str]) -> None:
    project_code = f"T{uuid.uuid4().hex[:5].upper()}"
    bad_code = f"{project_code}-EXGN0006-GGEN"
    line = "\t".join(
        [
            project_code,
            "E",
            "X",
            "GN",
            "00",
            "G",
            "GEN",
            "",
            "",
            "",
            bad_code,
        ]
    )

    response = client.post(
        "/api/v1/mdr/bulk-register",
        headers={**admin_headers, "Content-Type": "application/json"},
        json={"text_data": line},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True, body
    stats = body.get("stats", {})
    assert stats.get("success") == 0, body
    assert stats.get("failed") == 1, body
    detail = (stats.get("details") or [{}])[0]
    assert str(detail.get("status") or "").lower() == "failed"
    assert "01" in str(detail.get("msg") or "")


def _archive_seed_values(admin_headers: dict[str, str]) -> dict[str, str]:
    form_res = client.get("/api/v1/archive/form-data", headers=admin_headers)
    assert form_res.status_code == 200, form_res.text
    data = form_res.json()

    projects = data.get("projects") or []
    disciplines = data.get("disciplines") or []
    phases = data.get("phases") or []
    mdr_categories = data.get("mdr_categories") or []
    packages = data.get("packages") or []
    blocks = data.get("blocks") or []
    levels = data.get("levels") or []

    if not projects or not disciplines or not phases or not mdr_categories:
        pytest.skip("Archive lookup seed is incomplete for regression test.")

    project_code = str(projects[0].get("code") or "").strip().upper()
    discipline_code = str(disciplines[0].get("code") or "").strip().upper()
    phase_code = str(phases[0].get("code") or "").strip().upper()
    mdr_code = str(mdr_categories[0].get("code") or "").strip().upper()

    package_row = next(
        (p for p in packages if str(p.get("discipline_code") or "").strip().upper() == discipline_code),
        None,
    )
    if not package_row:
        pytest.skip("No package mapped to selected discipline in archive lookup seed.")
    package_code = str(package_row.get("code") or "").strip().upper()

    block_row = next(
        (b for b in blocks if str(b.get("project_code") or "").strip().upper() == project_code),
        None,
    )
    block_code = str((block_row or {}).get("code") or "G").strip().upper() or "G"

    level_code = "GEN"
    if levels:
        non_gen = next((str(v).strip().upper() for v in levels if str(v).strip().upper() != "GEN"), "")
        level_code = non_gen or str(levels[0]).strip().upper()

    return {
        "project_code": project_code,
        "discipline": discipline_code,
        "phase": phase_code,
        "mdr_code": mdr_code,
        "pkg": package_code,
        "block": block_code,
        "level": level_code or "GEN",
    }


def _archive_seed_with_unused_block(seed: dict[str, str]) -> dict[str, str]:
    result = dict(seed)
    with Session(engine) as db:
        for block_code in "ZYXWVUTSRQPONMLKJIHGFEDCBA":
            prefix, suffix = docnum_service.build_doc_number_parts(
                project_code=result["project_code"],
                mdr_code=result["mdr_code"],
                phase_code=result["phase"],
                discipline_code=result["discipline"],
                pkg_code=result["pkg"],
                block=block_code,
                level=result["level"],
            )
            exists = db.query(MdrDocument.id).filter(MdrDocument.doc_number.like(f"{prefix}%{suffix}")).first()
            if not exists:
                result["block"] = block_code
                return result
    return result


def test_regression_archive_next_serial_falls_back_to_subject_e(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_values(admin_headers)
    subject_e = f"EN-{uuid.uuid4().hex[:8]}"

    params = {
        **seed,
        "subject_e": subject_e,
        "subject_p": "",
    }

    preview_1 = client.get("/api/v1/archive/next-serial", params=params, headers=admin_headers)
    assert preview_1.status_code == 200, preview_1.text
    p1 = preview_1.json()
    doc_1 = str(p1.get("full_doc") or "").strip().upper()
    assert doc_1

    register_payload = {
        "doc_number": doc_1,
        "project_code": seed["project_code"],
        "mdr_code": seed["mdr_code"],
        "phase": seed["phase"],
        "discipline": seed["discipline"],
        "package": seed["pkg"],
        "block": seed["block"],
        "level": seed["level"],
        "subject_e": subject_e,
        "subject_p": "",
    }
    register_res = client.post("/api/v1/archive/register-document", data=register_payload, headers=admin_headers)
    assert register_res.status_code == 200, register_res.text

    preview_2 = client.get("/api/v1/archive/next-serial", params=params, headers=admin_headers)
    assert preview_2.status_code == 200, preview_2.text
    p2 = preview_2.json()
    assert p2.get("existing") is True
    assert str(p2.get("full_doc") or "").strip().upper() == doc_1
    assert int(p2.get("existing_document_id") or 0) > 0


def test_regression_archive_next_serial_subjectless_uses_one_serial(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_with_unused_block(_archive_seed_values(admin_headers))
    preview = client.get(
        "/api/v1/archive/next-serial",
        params={**seed, "subject_e": "", "subject_p": ""},
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    doc_number = str(body.get("full_doc") or "").strip().upper()
    serial = str(body.get("serial") or "").strip()
    assert doc_number
    assert serial == "01"

    if not body.get("existing"):
        register_res = client.post(
            "/api/v1/archive/register-document",
            data={
                "doc_number": doc_number,
                "project_code": seed["project_code"],
                "mdr_code": seed["mdr_code"],
                "phase": seed["phase"],
                "discipline": seed["discipline"],
                "package": seed["pkg"],
                "block": seed["block"],
                "level": seed["level"],
                "subject_e": "",
                "subject_p": "",
            },
            headers=admin_headers,
        )
        assert register_res.status_code == 200, register_res.text

    preview_2 = client.get(
        "/api/v1/archive/next-serial",
        params={**seed, "subject_e": "", "subject_p": ""},
        headers=admin_headers,
    )
    assert preview_2.status_code == 200, preview_2.text
    body2 = preview_2.json()
    assert body2.get("existing") is True
    assert str(body2.get("full_doc") or "").strip().upper() == doc_number
    assert str(body2.get("serial") or "").strip() == "01"


def test_regression_archive_next_serial_reuses_same_subject_metadata_key(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_values(admin_headers)
    subject_p = f"موضوع-تکرار-{uuid.uuid4().hex[:8]}"

    params = {
        **seed,
        "subject_e": "",
        "subject_p": subject_p,
    }

    preview_1 = client.get("/api/v1/archive/next-serial", params=params, headers=admin_headers)
    assert preview_1.status_code == 200, preview_1.text
    p1 = preview_1.json()
    doc_1 = str(p1.get("full_doc") or "").strip().upper()
    serial_1 = str(p1.get("serial") or "").strip()
    assert doc_1
    assert serial_1

    register_res = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": doc_1,
            "project_code": seed["project_code"],
            "mdr_code": seed["mdr_code"],
            "phase": seed["phase"],
            "discipline": seed["discipline"],
            "package": seed["pkg"],
            "block": seed["block"],
            "level": seed["level"],
            "subject_e": "",
            "subject_p": subject_p,
        },
        headers=admin_headers,
    )
    assert register_res.status_code == 200, register_res.text

    preview_2 = client.get("/api/v1/archive/next-serial", params=params, headers=admin_headers)
    assert preview_2.status_code == 200, preview_2.text
    p2 = preview_2.json()
    assert p2.get("existing") is True
    assert str(p2.get("full_doc") or "").strip().upper() == doc_1
    assert str(p2.get("serial") or "").strip() == serial_1
    assert int(p2.get("existing_document_id") or 0) > 0


def test_regression_archive_register_document_without_subject_reuses_existing_scope_doc(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_with_unused_block(_archive_seed_values(admin_headers))
    preview_subjectless = client.get(
        "/api/v1/archive/next-serial",
        params={**seed, "subject_e": "", "subject_p": ""},
        headers=admin_headers,
    )
    assert preview_subjectless.status_code == 200, preview_subjectless.text
    subjectless_body = preview_subjectless.json()
    subjectless_doc_number = str(subjectless_body.get("full_doc") or "").strip().upper()
    assert subjectless_doc_number
    if not subjectless_body.get("existing"):
        create_subjectless = client.post(
            "/api/v1/archive/register-document",
            data={
                "doc_number": subjectless_doc_number,
                "project_code": seed["project_code"],
                "mdr_code": seed["mdr_code"],
                "phase": seed["phase"],
                "discipline": seed["discipline"],
                "package": seed["pkg"],
                "block": seed["block"],
                "level": seed["level"],
                "subject_e": "",
                "subject_p": "",
            },
            headers=admin_headers,
        )
        assert create_subjectless.status_code == 200, create_subjectless.text

    candidate_doc_number = ""
    with Session(engine) as db:
        for forced_serial in range(99, 0, -1):
            doc_number, _ = docnum_service.generate_next_doc_number(
                db,
                project_code=seed["project_code"],
                mdr_code=seed["mdr_code"],
                phase_code=seed["phase"],
                discipline_code=seed["discipline"],
                pkg_code=seed["pkg"],
                block=seed["block"],
                level=seed["level"],
                subject_p=None,
                forced_serial=forced_serial,
            )
            exists = db.query(MdrDocument.id).filter(MdrDocument.doc_number == doc_number).first()
            if not exists:
                candidate_doc_number = str(doc_number or "").strip().upper()
                break
    assert candidate_doc_number

    register_res = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": candidate_doc_number,
            "project_code": seed["project_code"],
            "mdr_code": seed["mdr_code"],
            "phase": seed["phase"],
            "discipline": seed["discipline"],
            "package": seed["pkg"],
            "block": seed["block"],
            "level": seed["level"],
            "subject_e": "",
            "subject_p": "",
        },
        headers=admin_headers,
    )
    assert register_res.status_code == 200, register_res.text
    body = register_res.json()
    assert body.get("created") is False
    assert str(body.get("doc_number") or "").strip().upper() == subjectless_doc_number


def test_regression_archive_register_document_without_subject_rejects_non_zero_serial_when_no_subjectless_exists(
    admin_headers: dict[str, str],
) -> None:
    seed = _archive_seed_with_unused_block(_archive_seed_values(admin_headers))

    with Session(engine) as db:
        candidate_doc_number, _ = docnum_service.generate_next_doc_number(
            db,
            project_code=seed["project_code"],
            mdr_code=seed["mdr_code"],
            phase_code=seed["phase"],
            discipline_code=seed["discipline"],
            pkg_code=seed["pkg"],
            block=seed["block"],
            level=seed["level"],
            subject_p=None,
            forced_serial=6,
        )
    candidate_doc_number = str(candidate_doc_number or "").strip().upper()
    assert candidate_doc_number

    register_res = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": candidate_doc_number,
            "project_code": seed["project_code"],
            "mdr_code": seed["mdr_code"],
            "phase": seed["phase"],
            "discipline": seed["discipline"],
            "package": seed["pkg"],
            "block": seed["block"],
            "level": seed["level"],
            "subject_e": "",
            "subject_p": "",
        },
        headers=admin_headers,
    )
    assert register_res.status_code == 422, register_res.text
    assert "01" in register_res.text


def test_regression_archive_next_serial_increments_for_new_subject(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_values(admin_headers)
    subject_p_1 = f"موضوع-جدید-۱-{uuid.uuid4().hex[:8]}"
    subject_p_2 = f"موضوع-جدید-۲-{uuid.uuid4().hex[:8]}"

    params_1 = {**seed, "subject_e": "", "subject_p": subject_p_1}
    preview_1 = client.get("/api/v1/archive/next-serial", params=params_1, headers=admin_headers)
    assert preview_1.status_code == 200, preview_1.text
    p1 = preview_1.json()
    doc_1 = str(p1.get("full_doc") or "").strip().upper()
    serial_1 = str(p1.get("serial") or "").strip()
    assert doc_1
    assert serial_1

    register_1 = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": doc_1,
            "project_code": seed["project_code"],
            "mdr_code": seed["mdr_code"],
            "phase": seed["phase"],
            "discipline": seed["discipline"],
            "package": seed["pkg"],
            "block": seed["block"],
            "level": seed["level"],
            "subject_e": "",
            "subject_p": subject_p_1,
        },
        headers=admin_headers,
    )
    assert register_1.status_code == 200, register_1.text

    params_2 = {**seed, "subject_e": "", "subject_p": subject_p_2}
    preview_2 = client.get("/api/v1/archive/next-serial", params=params_2, headers=admin_headers)
    assert preview_2.status_code == 200, preview_2.text
    p2 = preview_2.json()
    assert p2.get("existing") is False
    serial_2 = str(p2.get("serial") or "").strip()
    assert serial_2
    assert int(serial_2) == int(serial_1) + 1


def test_regression_archive_register_document_titles_follow_coding_rule(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_values(admin_headers)
    subject_e = f"TitleEN-{uuid.uuid4().hex[:6]}"
    subject_p = f"موضوع-{uuid.uuid4().hex[:6]}"
    canonical_subject = subject_p

    preview = client.get(
        "/api/v1/archive/next-serial",
        params={**seed, "subject_e": subject_e, "subject_p": subject_p},
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    doc_number = str(body.get("full_doc") or "").strip().upper()
    assert doc_number

    register_res = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": doc_number,
            "project_code": seed["project_code"],
            "mdr_code": seed["mdr_code"],
            "phase": seed["phase"],
            "discipline": seed["discipline"],
            "package": seed["pkg"],
            "block": seed["block"],
            "level": seed["level"],
            "subject_e": subject_e,
            "subject_p": subject_p,
        },
        headers=admin_headers,
    )
    assert register_res.status_code == 200, register_res.text

    with Session(engine) as db:
        row = db.query(MdrDocument).filter(MdrDocument.doc_number == doc_number).first()
        assert row is not None
        expected_e, expected_p = mdr_service.build_document_titles(
            db,
            discipline_code=seed["discipline"],
            package_code=seed["pkg"],
            block_code=seed["block"],
            level_code=seed["level"],
            subject_e=canonical_subject,
            subject_p=canonical_subject,
        )
        assert row.doc_title_e == expected_e
        assert row.doc_title_p == expected_p
        assert (row.subject or "") == canonical_subject


def test_regression_archive_register_document_uses_single_subject_value(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_values(admin_headers)
    single_subject = f"Single-{uuid.uuid4().hex[:8]}"

    preview = client.get(
        "/api/v1/archive/next-serial",
        params={**seed, "subject_e": single_subject, "subject_p": ""},
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    doc_number = str(preview.json().get("full_doc") or "").strip().upper()
    assert doc_number

    register_res = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": doc_number,
            "project_code": seed["project_code"],
            "mdr_code": seed["mdr_code"],
            "phase": seed["phase"],
            "discipline": seed["discipline"],
            "package": seed["pkg"],
            "block": seed["block"],
            "level": seed["level"],
            "subject_e": single_subject,
            "subject_p": "",
        },
        headers=admin_headers,
    )
    assert register_res.status_code == 200, register_res.text

    with Session(engine) as db:
        row = db.query(MdrDocument).filter(MdrDocument.doc_number == doc_number).first()
        assert row is not None
        expected_e, expected_p = mdr_service.build_document_titles(
            db,
            discipline_code=seed["discipline"],
            package_code=seed["pkg"],
            block_code=seed["block"],
            level_code=seed["level"],
            subject_e=single_subject,
            subject_p=single_subject,
        )
        assert row.doc_title_e == expected_e
        assert row.doc_title_p == expected_p
        assert (row.subject or "") == single_subject


def test_regression_build_titles_uses_block_plus_level_for_title_p(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_values(admin_headers)
    with Session(engine) as db:
        level = (
            db.query(Level)
            .filter(Level.code != "GEN")
            .first()
        )
        if level is None or not str(level.code or "").strip():
            pytest.skip("No non-GEN level code exists.")

        _, title_p = mdr_service.build_document_titles(
            db,
            discipline_code=seed["discipline"],
            package_code=seed["pkg"],
            block_code=seed["block"],
            level_code=str(level.code or "").strip().upper(),
            subject_e="",
            subject_p="موضوع تست",
        )
        assert title_p.startswith(f"{seed['block']}{level.code}-")


def test_regression_build_titles_omits_location_only_for_t_gen(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_values(admin_headers)
    with Session(engine) as db:
        title_e, title_p = mdr_service.build_document_titles(
            db,
            discipline_code=seed["discipline"],
            package_code=seed["pkg"],
            block_code="T",
            level_code="GEN",
            subject_e="Subject",
            subject_p="Subject",
        )
        assert "TGEN" not in title_e
        assert not title_p.startswith("TGEN-")

        title_e, title_p = mdr_service.build_document_titles(
            db,
            discipline_code=seed["discipline"],
            package_code=seed["pkg"],
            block_code="B",
            level_code="GEN",
            subject_e="Subject",
            subject_p="Subject",
        )
        assert "-BGEN" in title_e
        assert title_p.startswith("BGEN-")


def test_regression_build_titles_normalizes_prefixed_package_code(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_values(admin_headers)
    prefixed_pkg = f"{seed['discipline']}{seed['pkg']}"

    with Session(engine) as db:
        pkg_row = (
            db.query(Package)
            .filter(Package.discipline_code == seed["discipline"])
            .filter(Package.package_code == seed["pkg"])
            .first()
        )
        if pkg_row is None:
            pytest.skip("No package row found for selected discipline/package.")
        expected_name_e = str(pkg_row.name_e or "").strip()
        expected_name_p = str(pkg_row.name_p or expected_name_e).strip()
        if not expected_name_e:
            pytest.skip("Package name_e is empty for selected row.")

        title_e, title_p = mdr_service.build_document_titles(
            db,
            discipline_code=seed["discipline"],
            package_code=prefixed_pkg,
            block_code=seed["block"],
            level_code=seed["level"],
            subject_e="",
            subject_p="",
        )
        assert expected_name_e in title_e
        assert expected_name_p in title_p


def test_regression_archive_register_normalizes_prefixed_package_code(admin_headers: dict[str, str]) -> None:
    seed = _archive_seed_values(admin_headers)
    prefixed_pkg = f"{seed['discipline']}{seed['pkg']}"
    subject_p = f"بسته-{uuid.uuid4().hex[:6]}"

    preview = client.get(
        "/api/v1/archive/next-serial",
        params={**seed, "pkg": prefixed_pkg, "subject_e": "", "subject_p": subject_p},
        headers=admin_headers,
    )
    assert preview.status_code == 200, preview.text
    doc_number = str(preview.json().get("full_doc") or "").strip().upper()
    assert doc_number

    register = client.post(
        "/api/v1/archive/register-document",
        data={
            "doc_number": doc_number,
            "project_code": seed["project_code"],
            "mdr_code": seed["mdr_code"],
            "phase": seed["phase"],
            "discipline": seed["discipline"],
            "package": prefixed_pkg,
            "block": seed["block"],
            "level": seed["level"],
            "subject_e": "",
            "subject_p": subject_p,
        },
        headers=admin_headers,
    )
    assert register.status_code == 200, register.text

    with Session(engine) as db:
        row = db.query(MdrDocument).filter(MdrDocument.doc_number == doc_number).first()
        assert row is not None
        pkg_row = (
            db.query(Package)
            .filter(Package.discipline_code == seed["discipline"])
            .filter(Package.package_code == seed["pkg"])
            .first()
        )
        assert pkg_row is not None
        assert (row.package_code or "").upper() == seed["pkg"].upper()
        assert (row.doc_title_e or "").startswith(str(pkg_row.name_e or pkg_row.package_code))
