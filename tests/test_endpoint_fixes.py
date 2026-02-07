import uuid

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import get_auth_headers

client = TestClient(app)


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


def test_lookup_dictionary_endpoint_available():
    response = client.get("/api/v1/lookup/dictionary")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True
    assert isinstance(body.get("data"), dict)


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
