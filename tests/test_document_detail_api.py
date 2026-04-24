from __future__ import annotations

from copy import deepcopy
import io
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import UserDisciplineScope, UserProjectScope
from app.db.session import SessionLocal
from app.main import app
from tests.auth_helpers import get_auth_headers
from tests.site_logs_helpers import ensure_org


client = TestClient(app)

PROJECT_CODE = "TSEED"
DISCIPLINE_CODE = "GN"


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


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
            "organization_role": "viewer",
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

    update_response = client.put(
        f"/api/v1/archive/documents/{document_id}",
        json={
            "doc_title_e": "Updated Title API",
            "subject": "Updated Subject API",
            "notes": "Updated Notes API",
        },
        headers=admin,
    )
    assert update_response.status_code == 200, update_response.text
    updated_doc = update_response.json().get("document") or {}
    assert updated_doc.get("doc_title_e") == "Updated Title API"
    assert updated_doc.get("subject") == "Updated Subject API"
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

        reused_tag = client.post(
            "/api/v1/archive/tags",
            json={"name": "qa-tag"},
            headers=scoped_headers,
        )
        assert reused_tag.status_code == 200, reused_tag.text
        assert int((reused_tag.json().get("tag") or {}).get("id") or 0) == tag_id

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
