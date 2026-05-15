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
    projects = client.get("/api/v1/settings/projects", headers=headers).json().get("items", [])
    if projects:
        project_code = str(projects[0].get("code") or projects[0].get("project_code") or "").strip().upper()
    else:
        project_code = f"WIP{uuid4().hex[:4].upper()}"
        res = client.post(
            "/api/v1/settings/projects/upsert",
            json={"code": project_code, "name_e": f"Project {project_code}", "is_active": True},
            headers=headers,
        )
        assert res.status_code == 200, res.text

    disciplines = client.get("/api/v1/settings/disciplines", headers=headers).json().get("items", [])
    if disciplines:
        discipline_code = str(disciplines[0].get("code") or "").strip().upper()
    else:
        discipline_code = f"D{uuid4().hex[:3].upper()}"
        res = client.post(
            "/api/v1/settings/disciplines/upsert",
            json={"code": discipline_code, "name_e": f"Discipline {discipline_code}"},
            headers=headers,
        )
        assert res.status_code == 200, res.text

    orgs = client.get("/api/v1/settings/organizations", headers=headers).json().get("items", [])
    if orgs:
        org_id = int(orgs[0].get("id") or 0)
    else:
        org_code = f"WIORG{uuid4().hex[:4].upper()}"
        res = client.post(
            "/api/v1/settings/organizations/upsert",
            json={"code": org_code, "name": f"Org {org_code}", "org_type": "consultant", "is_active": True},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        org_id = int(res.json().get("id") or 0)

    assert project_code and discipline_code and org_id > 0
    return project_code, discipline_code, org_id


def _create_instruction(headers: dict[str, str], project_code: str, discipline_code: str, org_id: int) -> int:
    payload = {
        "project_code": project_code,
        "discipline_code": discipline_code,
        "recipient_org_id": org_id,
        "title": f"Work instruction {uuid4().hex[:6]}",
        "description": "Execute the listed technical instruction with consultant coordination.",
        "required_action": "Prepare method statement and proceed after site confirmation.",
        "response_due_date": (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%dT00:00:00"),
        "priority": "NORMAL",
    }
    res = client.post("/api/v1/work-instructions/create", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    instruction_id = int(body.get("data", {}).get("id") or 0)
    assert instruction_id > 0
    assert body.get("data", {}).get("instruction_no")
    return instruction_id


def test_work_instruction_catalog_create_update_transition_attachment_relation() -> None:
    headers = _admin_headers()
    project_code, discipline_code, org_id = _ensure_context(headers)

    catalog = client.get("/api/v1/work-instructions/catalog", headers=headers)
    assert catalog.status_code == 200, catalog.text
    assert catalog.json().get("ok") is True
    assert "DRAFT" in {row.get("code") for row in catalog.json().get("workflow_statuses", [])}

    instruction_id = _create_instruction(headers, project_code, discipline_code, org_id)

    update = client.put(
        f"/api/v1/work-instructions/{instruction_id}",
        json={"title": f"Updated instruction {uuid4().hex[:6]}", "priority": "HIGH"},
        headers=headers,
    )
    assert update.status_code == 200, update.text
    assert update.json().get("data", {}).get("priority") == "HIGH"

    submit = client.post(
        f"/api/v1/work-instructions/{instruction_id}/transition",
        json={"to_status_code": "SUBMITTED"},
        headers=headers,
    )
    assert submit.status_code == 200, submit.text
    assert submit.json().get("data", {}).get("status_code") == "SUBMITTED"

    attachment = client.post(
        f"/api/v1/work-instructions/{instruction_id}/attachments",
        files={"file": ("wi-note.txt", b"work instruction attachment", "text/plain")},
        data={"file_kind": "attachment", "scope_code": "GENERAL"},
        headers=headers,
    )
    assert attachment.status_code == 200, attachment.text
    attachment_id = int(attachment.json().get("data", {}).get("id") or 0)
    assert attachment_id > 0
    download = client.get(f"/api/v1/work-instructions/attachments/{attachment_id}/download", headers=headers)
    assert download.status_code == 200, download.text

    target_id = _create_instruction(headers, project_code, discipline_code, org_id)
    relation = client.post(
        f"/api/v1/work-instructions/{instruction_id}/relations",
        json={"target_type": "work_instruction", "target_id": target_id, "relation_type": "REFERENCES"},
        headers=headers,
    )
    assert relation.status_code == 200, relation.text
    relations = client.get(f"/api/v1/work-instructions/{instruction_id}/relations", headers=headers)
    assert relations.status_code == 200, relations.text
    assert relations.json().get("outgoing")


def test_comm_items_no_longer_accept_tech() -> None:
    headers = _admin_headers()
    project_code, discipline_code, org_id = _ensure_context(headers)
    res = client.post(
        "/api/v1/comm-items/create",
        json={
            "item_type": "TECH",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "title": f"TECH rejected {uuid4().hex[:6]}",
            "recipient_org_id": org_id,
            "tech": {"tech_subtype_code": "INSTRUCTION"},
        },
        headers=headers,
    )
    assert res.status_code == 400, res.text
    assert "Unsupported item_type" in res.text
