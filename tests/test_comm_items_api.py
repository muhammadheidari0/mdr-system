from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _ensure_context(headers: dict[str, str]) -> tuple[str, str, int]:
    projects_res = client.get("/api/v1/settings/projects", headers=headers)
    assert projects_res.status_code == 200, projects_res.text
    projects = projects_res.json().get("items", [])
    if not projects:
        code = f"UTP{uuid4().hex[:4].upper()}"
        upsert = client.post(
            "/api/v1/settings/projects/upsert",
            json={"code": code, "name_e": f"Project {code}", "is_active": True},
            headers=headers,
        )
        assert upsert.status_code == 200, upsert.text
        project_code = code
    else:
        project_code = str(projects[0].get("code") or projects[0].get("project_code") or "").strip().upper()

    disciplines_res = client.get("/api/v1/settings/disciplines", headers=headers)
    assert disciplines_res.status_code == 200, disciplines_res.text
    disciplines = disciplines_res.json().get("items", [])
    if not disciplines:
        dcode = f"D{uuid4().hex[:3].upper()}"
        upsert = client.post(
            "/api/v1/settings/disciplines/upsert",
            json={"code": dcode, "name_e": f"Discipline {dcode}"},
            headers=headers,
        )
        assert upsert.status_code == 200, upsert.text
        discipline_code = dcode
    else:
        discipline_code = str(disciplines[0].get("code") or disciplines[0].get("discipline_code") or "").strip().upper()

    org_res = client.get("/api/v1/settings/organizations", headers=headers)
    assert org_res.status_code == 200, org_res.text
    org_items = org_res.json().get("items", [])
    if not org_items:
        org_code = f"ORG{uuid4().hex[:4].upper()}"
        upsert = client.post(
            "/api/v1/settings/organizations/upsert",
            json={"code": org_code, "name": f"Org {org_code}", "org_type": "contractor", "is_active": True},
            headers=headers,
        )
        assert upsert.status_code == 200, upsert.text
        org_id = int(upsert.json().get("id") or 0)
    else:
        org_id = int(org_items[0].get("id") or 0)

    assert project_code
    assert discipline_code
    assert org_id > 0
    return project_code, discipline_code, org_id


def _create_tech_item(headers: dict[str, str], project_code: str, discipline_code: str) -> int:
    payload = {
        "item_type": "TECH",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"TECH relation {uuid4().hex[:6]}",
        "status_code": "DRAFT",
        "priority": "NORMAL",
        "tech": {
            "tech_subtype_code": "INSTRUCTION",
            "document_no": f"DOC-{uuid4().hex[:4].upper()}",
            "revision": "A",
        },
    }
    res = client.post("/api/v1/comm-items/create", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    return int(body.get("data", {}).get("id"))


def test_comm_items_crud_relation_and_attachment_flow() -> None:
    headers = _admin_headers()
    project_code, discipline_code, recipient_org_id = _ensure_context(headers)

    due = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%dT00:00:00")
    create_payload = {
        "item_type": "RFI",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"RFI smoke {uuid4().hex[:6]}",
        "status_code": "DRAFT",
        "priority": "NORMAL",
        "response_due_date": due,
        "recipient_org_id": recipient_org_id,
        "rfi": {
            "question_text": "Please clarify structural detail at the interface for work execution.",
            "proposed_solution": "Contractor proposes detail D-12 as baseline.",
        },
    }

    create_res = client.post("/api/v1/comm-items/create", json=create_payload, headers=headers)
    assert create_res.status_code == 200, create_res.text
    create_body = create_res.json()
    assert create_body.get("ok") is True
    item_id = int(create_body.get("data", {}).get("id") or 0)
    assert item_id > 0

    list_res = client.get(
        "/api/v1/comm-items/list?module_key=contractor&tab_key=requests&skip=0&limit=50",
        headers=headers,
    )
    assert list_res.status_code == 200, list_res.text
    list_body = list_res.json()
    assert list_body.get("ok") is True
    rows = list_body.get("data", [])
    assert any(int(row.get("id", 0)) == item_id for row in rows)

    update_res = client.put(
        f"/api/v1/comm-items/{item_id}",
        json={"priority": "HIGH", "impact_note": "Potential sequence impact"},
        headers=headers,
    )
    assert update_res.status_code == 200, update_res.text
    update_body = update_res.json()
    assert update_body.get("ok") is True
    assert update_body.get("data", {}).get("priority") == "HIGH"

    comment_res = client.post(
        f"/api/v1/comm-items/{item_id}/comments",
        json={"comment_text": "Follow-up required", "comment_type": "action"},
        headers=headers,
    )
    assert comment_res.status_code == 200, comment_res.text
    assert comment_res.json().get("ok") is True

    attachment_upload = client.post(
        f"/api/v1/comm-items/{item_id}/attachments",
        data={
            "file_kind": "attachment",
            "scope_code": "REFERENCE",
            "slot_code": "RFI_REFERENCE",
            "note": "reference package",
        },
        files={"file": ("note.txt", b"smoke attachment", "text/plain")},
        headers=headers,
    )
    assert attachment_upload.status_code == 200, attachment_upload.text
    attachment_body = attachment_upload.json()
    attachment_id = int(attachment_body.get("data", {}).get("id") or 0)
    assert attachment_id > 0
    assert attachment_body.get("data", {}).get("scope_code") == "REFERENCE"
    assert attachment_body.get("data", {}).get("slot_code") == "RFI_REFERENCE"

    attachments_res = client.get(f"/api/v1/comm-items/{item_id}/attachments", headers=headers)
    assert attachments_res.status_code == 200, attachments_res.text
    attachments_body = attachments_res.json()
    attachments = attachments_body.get("data", [])
    assert any(int(row.get("id", 0)) == attachment_id for row in attachments)
    grouped = attachments_body.get("grouped", {})
    assert isinstance(grouped, dict)
    assert "REFERENCE" in grouped

    delete_attachment = client.delete(
        f"/api/v1/comm-items/{item_id}/attachments?attachment_id={attachment_id}",
        headers=headers,
    )
    assert delete_attachment.status_code == 200, delete_attachment.text

    second_item_id = _create_tech_item(headers, project_code, discipline_code)

    relation_create = client.post(
        f"/api/v1/comm-items/{item_id}/relations",
        json={"to_item_id": second_item_id, "relation_type": "REFERENCES", "note": "linked in smoke test"},
        headers=headers,
    )
    assert relation_create.status_code == 200, relation_create.text
    relation_id = int(relation_create.json().get("data", {}).get("id") or 0)
    assert relation_id > 0

    relations_res = client.get(f"/api/v1/comm-items/{item_id}/relations", headers=headers)
    assert relations_res.status_code == 200, relations_res.text
    outgoing = relations_res.json().get("outgoing", [])
    assert any(int(row.get("id", 0)) == relation_id for row in outgoing)

    relation_delete = client.delete(
        f"/api/v1/comm-items/{item_id}/relations?relation_id={relation_id}",
        headers=headers,
    )
    assert relation_delete.status_code == 200, relation_delete.text


def test_comm_items_reject_cross_type_detail_payloads() -> None:
    headers = _admin_headers()
    project_code, discipline_code, recipient_org_id = _ensure_context(headers)

    rfi_wrong = {
        "item_type": "RFI",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"RFI wrong {uuid4().hex[:6]}",
        "status_code": "DRAFT",
        "recipient_org_id": recipient_org_id,
        "rfi": {"question_text": "Valid RFI question body for this payload test case."},
        "ncr": {
            "kind": "NCR",
            "severity": "MINOR",
            "nonconformance_text": "This should be rejected because type is RFI.",
        },
    }
    rfi_wrong_res = client.post("/api/v1/comm-items/create", json=rfi_wrong, headers=headers)
    assert rfi_wrong_res.status_code == 400, rfi_wrong_res.text

    ncr_wrong = {
        "item_type": "NCR",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"NCR wrong {uuid4().hex[:6]}",
        "status_code": "ISSUED",
        "ncr": {
            "kind": "NCR",
            "severity": "MAJOR",
            "nonconformance_text": "Valid NCR body for payload type mismatch testing purpose.",
        },
        "tech": {
            "tech_subtype_code": "INSTRUCTION",
            "document_no": f"DOC-{uuid4().hex[:4].upper()}",
            "revision": "A",
        },
    }
    ncr_wrong_res = client.post("/api/v1/comm-items/create", json=ncr_wrong, headers=headers)
    assert ncr_wrong_res.status_code == 400, ncr_wrong_res.text

    tech_wrong = {
        "item_type": "TECH",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"TECH wrong {uuid4().hex[:6]}",
        "status_code": "DRAFT",
        "tech": {
            "tech_subtype_code": "INSTRUCTION",
            "document_no": f"DOC-{uuid4().hex[:4].upper()}",
            "revision": "A",
        },
        "rfi": {"question_text": "This should fail because TECH cannot include RFI detail."},
    }
    tech_wrong_res = client.post("/api/v1/comm-items/create", json=tech_wrong, headers=headers)
    assert tech_wrong_res.status_code == 400, tech_wrong_res.text


def test_comm_items_attachment_slot_validation_and_real_formats() -> None:
    headers = _admin_headers()
    project_code, discipline_code, _recipient_org_id = _ensure_context(headers)

    create_payload = {
        "item_type": "NCR",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"NCR attach {uuid4().hex[:6]}",
        "status_code": "ISSUED",
        "ncr": {
            "kind": "NCR",
            "severity": "MAJOR",
            "nonconformance_text": "Nonconformance details for attachment slot validation test case.",
        },
    }
    create_res = client.post("/api/v1/comm-items/create", json=create_payload, headers=headers)
    assert create_res.status_code == 200, create_res.text
    item_id = int(create_res.json().get("data", {}).get("id") or 0)
    assert item_id > 0

    wrong_slot_res = client.post(
        f"/api/v1/comm-items/{item_id}/attachments",
        data={
            "file_kind": "attachment",
            "scope_code": "RESPONSE",
            "slot_code": "RFI_RESPONSE",
        },
        files={"file": ("wrong-slot.txt", b"invalid slot", "text/plain")},
        headers=headers,
    )
    assert wrong_slot_res.status_code == 400, wrong_slot_res.text

    files_to_upload = [
        ("sample.pdf", b"%PDF-1.4\n%test\n", "application/pdf", "attachment"),
        ("sample.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg", "attachment"),
        ("sample.xlsx", b"PK\x03\x04xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "native"),
        ("sample.dwg", b"AC1018DWG", "application/x-dwg", "native"),
        ("sample.dxf", b"0\nSECTION\n2\nHEADER\n", "application/dxf", "native"),
        ("sample.ifc", b"ISO-10303-21;\nHEADER;\n", "model/ifc", "native"),
        ("sample.zip", b"PK\x03\x04zip", "application/zip", "native"),
    ]

    for file_name, content, mime, kind in files_to_upload:
        upload_res = client.post(
            f"/api/v1/comm-items/{item_id}/attachments",
            data={
                "file_kind": kind,
                "scope_code": "REFERENCE",
                "slot_code": "NCR_REFERENCE",
            },
            files={"file": (file_name, content, mime)},
            headers=headers,
        )
        assert upload_res.status_code == 200, f"{file_name}: {upload_res.text}"

    dangerous_res = client.post(
        f"/api/v1/comm-items/{item_id}/attachments",
        data={
            "file_kind": "attachment",
            "scope_code": "REFERENCE",
            "slot_code": "NCR_REFERENCE",
        },
        files={"file": ("danger.exe", b"MZbad", "application/octet-stream")},
        headers=headers,
    )
    assert dangerous_res.status_code == 422, dangerous_res.text

    list_has_ref = client.get(
        f"/api/v1/comm-items/list?item_type=NCR&has_reference_attachments=true&project_code={project_code}&discipline_code={discipline_code}",
        headers=headers,
    )
    assert list_has_ref.status_code == 200, list_has_ref.text
    rows = list_has_ref.json().get("data", [])
    assert any(int(row.get("id", 0)) == item_id for row in rows)

    list_attachment_cad = client.get(
        f"/api/v1/comm-items/list?item_type=NCR&attachment_type=cad&project_code={project_code}&discipline_code={discipline_code}",
        headers=headers,
    )
    assert list_attachment_cad.status_code == 200, list_attachment_cad.text


def test_comm_items_alias_params_precedence_and_impact_alias_endpoint() -> None:
    headers = _admin_headers()
    project_code, discipline_code, _recipient_org_id = _ensure_context(headers)

    plain_payload = {
        "item_type": "TECH",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"TECH plain {uuid4().hex[:6]}",
        "status_code": "DRAFT",
        "tech": {
            "tech_subtype_code": "INSTRUCTION",
            "document_no": f"DOC-{uuid4().hex[:4].upper()}",
            "revision": "A",
        },
    }
    impact_payload = {
        "item_type": "TECH",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"TECH impact {uuid4().hex[:6]}",
        "status_code": "DRAFT",
        "potential_impact_time": True,
        "tech": {
            "tech_subtype_code": "INSTRUCTION",
            "document_no": f"DOC-{uuid4().hex[:4].upper()}",
            "revision": "A",
        },
    }
    plain_res = client.post("/api/v1/comm-items/create", json=plain_payload, headers=headers)
    assert plain_res.status_code == 200, plain_res.text
    plain_id = int(plain_res.json().get("data", {}).get("id") or 0)
    assert plain_id > 0

    impact_res = client.post("/api/v1/comm-items/create", json=impact_payload, headers=headers)
    assert impact_res.status_code == 200, impact_res.text
    impact_id = int(impact_res.json().get("data", {}).get("id") or 0)
    assert impact_id > 0

    claim_only_res = client.get(
        f"/api/v1/comm-items/list?project_code={project_code}&discipline_code={discipline_code}&item_type=TECH&claim_only=true",
        headers=headers,
    )
    assert claim_only_res.status_code == 200, claim_only_res.text
    claim_rows = claim_only_res.json().get("data", [])
    assert any(int(row.get("id", 0)) == impact_id for row in claim_rows)

    alias_precedence_res = client.get(
        f"/api/v1/comm-items/list?project_code={project_code}&discipline_code={discipline_code}&item_type=TECH&claim_only=true&impact_only=false",
        headers=headers,
    )
    assert alias_precedence_res.status_code == 200, alias_precedence_res.text
    alias_rows = alias_precedence_res.json().get("data", [])
    assert any(int(row.get("id", 0)) == plain_id for row in alias_rows)

    control_default_res = client.get(
        f"/api/v1/comm-items/list?module_key=consultant&tab_key=control&project_code={project_code}&discipline_code={discipline_code}&item_type=TECH",
        headers=headers,
    )
    assert control_default_res.status_code == 200, control_default_res.text
    control_default_rows = control_default_res.json().get("data", [])
    assert all(int(row.get("id", 0)) != plain_id for row in control_default_rows)

    control_alias_res = client.get(
        "/api/v1/comm-items/list"
        f"?module_key=consultant&tab_key=control&project_code={project_code}&discipline_code={discipline_code}"
        "&item_type=TECH&include_non_claim_control=false&include_non_impact_control=true",
        headers=headers,
    )
    assert control_alias_res.status_code == 200, control_alias_res.text
    control_alias_rows = control_alias_res.json().get("data", [])
    assert any(int(row.get("id", 0)) == plain_id for row in control_alias_rows)

    alias_endpoint_res = client.get(
        f"/api/v1/comm-items/reports/impact-signals?project_code={project_code}&discipline_code={discipline_code}&item_type=TECH",
        headers=headers,
    )
    legacy_endpoint_res = client.get(
        f"/api/v1/comm-items/reports/claim-candidates?project_code={project_code}&discipline_code={discipline_code}&item_type=TECH",
        headers=headers,
    )
    assert alias_endpoint_res.status_code == 200, alias_endpoint_res.text
    assert legacy_endpoint_res.status_code == 200, legacy_endpoint_res.text
    assert int(alias_endpoint_res.json().get("count", 0)) == int(legacy_endpoint_res.json().get("count", 0))


def test_comm_items_lite_mode_allows_impact_update_without_hard_lock() -> None:
    headers = _admin_headers()
    project_code, discipline_code, _recipient_org_id = _ensure_context(headers)

    create_payload = {
        "item_type": "TECH",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"TECH policy {uuid4().hex[:6]}",
        "status_code": "DRAFT",
        "tech": {
            "tech_subtype_code": "INSTRUCTION",
            "document_no": f"DOC-{uuid4().hex[:4].upper()}",
            "revision": "A",
        },
    }
    create_res = client.post("/api/v1/comm-items/create", json=create_payload, headers=headers)
    assert create_res.status_code == 200, create_res.text
    item_id = int(create_res.json().get("data", {}).get("id") or 0)
    assert item_id > 0

    update_res = client.put(
        f"/api/v1/comm-items/{item_id}",
        json={"potential_impact_time": True},
        headers=headers,
    )
    assert update_res.status_code == 200, update_res.text
    assert bool(update_res.json().get("data", {}).get("potential_impact_time")) is True
