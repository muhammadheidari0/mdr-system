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
    if not projects:
        code = f"WFP{uuid4().hex[:4].upper()}"
        res = client.post(
            "/api/v1/settings/projects/upsert",
            json={"code": code, "name_e": f"Project {code}", "is_active": True},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        project_code = code
    else:
        project_code = str(projects[0].get("code") or projects[0].get("project_code") or "").strip().upper()

    disciplines = client.get("/api/v1/settings/disciplines", headers=headers).json().get("items", [])
    if not disciplines:
        code = f"WD{uuid4().hex[:3].upper()}"
        res = client.post(
            "/api/v1/settings/disciplines/upsert",
            json={"code": code, "name_e": f"Discipline {code}"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        discipline_code = code
    else:
        discipline_code = str(disciplines[0].get("code") or "").strip().upper()

    orgs = client.get("/api/v1/settings/organizations", headers=headers).json().get("items", [])
    if not orgs:
        code = f"WORG{uuid4().hex[:4].upper()}"
        res = client.post(
            "/api/v1/settings/organizations/upsert",
            json={"code": code, "name": f"Org {code}", "org_type": "contractor", "is_active": True},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        org_id = int(res.json().get("id") or 0)
    else:
        org_id = int(orgs[0].get("id") or 0)

    assert project_code and discipline_code and org_id > 0
    return project_code, discipline_code, org_id


def _create_valid_rfi(headers: dict[str, str], project_code: str, discipline_code: str, org_id: int) -> int:
    payload = {
        "item_type": "RFI",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"RFI wf {uuid4().hex[:6]}",
        "status_code": "DRAFT",
        "priority": "NORMAL",
        "response_due_date": (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%dT00:00:00"),
        "recipient_org_id": org_id,
        "rfi": {
            "question_text": "Please provide full technical clarification for this request item.",
        },
    }
    res = client.post("/api/v1/comm-items/create", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    return int(res.json().get("data", {}).get("id") or 0)


def test_rfi_submitted_without_question_text_rejected() -> None:
    headers = _admin_headers()
    project_code, discipline_code, org_id = _ensure_context(headers)

    payload = {
        "item_type": "RFI",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"RFI invalid {uuid4().hex[:6]}",
        "status_code": "SUBMITTED",
        "priority": "NORMAL",
        "response_due_date": (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%dT00:00:00"),
        "recipient_org_id": org_id,
        "rfi": {
            "question_text": "",
        },
    }

    res = client.post("/api/v1/comm-items/create", json=payload, headers=headers)
    assert res.status_code == 400, res.text


def test_rfi_answer_without_answer_text_rejected() -> None:
    headers = _admin_headers()
    project_code, discipline_code, org_id = _ensure_context(headers)

    item_id = _create_valid_rfi(headers, project_code, discipline_code, org_id)
    for status in ["SUBMITTED", "IN_REVIEW"]:
        trans = client.post(
            f"/api/v1/comm-items/{item_id}/transition",
            json={"to_status_code": status},
            headers=headers,
        )
        assert trans.status_code == 200, trans.text

    answered = client.post(
        f"/api/v1/comm-items/{item_id}/transition",
        json={"to_status_code": "ANSWERED"},
        headers=headers,
    )
    assert answered.status_code == 400, answered.text


def test_ncr_verified_without_verification_note_rejected() -> None:
    headers = _admin_headers()
    project_code, discipline_code, _org_id = _ensure_context(headers)

    payload = {
        "item_type": "NCR",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"NCR wf {uuid4().hex[:6]}",
        "status_code": "ISSUED",
        "ncr": {
            "kind": "NCR",
            "severity": "MAJOR",
            "nonconformance_text": "Nonconformance details are documented with enough text for validation.",
            "rectification_method": "Repair and retest with consultant witness.",
        },
    }
    create_res = client.post("/api/v1/comm-items/create", json=payload, headers=headers)
    assert create_res.status_code == 200, create_res.text
    item_id = int(create_res.json().get("data", {}).get("id") or 0)

    for status in ["CONTRACTOR_REPLY", "ACCEPTED", "RECTIFIED"]:
        trans = client.post(
            f"/api/v1/comm-items/{item_id}/transition",
            json={"to_status_code": status},
            headers=headers,
        )
        assert trans.status_code == 200, trans.text

    verified = client.post(
        f"/api/v1/comm-items/{item_id}/transition",
        json={"to_status_code": "VERIFIED"},
        headers=headers,
    )
    assert verified.status_code == 400, verified.text


def test_tech_submittal_without_document_no_revision_rejected() -> None:
    headers = _admin_headers()
    project_code, discipline_code, org_id = _ensure_context(headers)

    payload = {
        "item_type": "TECH",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"TECH invalid {uuid4().hex[:6]}",
        "status_code": "SUBMITTED",
        "response_due_date": (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%dT00:00:00"),
        "recipient_org_id": org_id,
        "tech": {
            "tech_subtype_code": "SUBMITTAL",
        },
    }

    res = client.post("/api/v1/comm-items/create", json=payload, headers=headers)
    assert res.status_code == 400, res.text


def test_tech_report_submitted_without_recipient_or_due_rejected() -> None:
    headers = _admin_headers()
    project_code, discipline_code, _org_id = _ensure_context(headers)

    payload = {
        "item_type": "TECH",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"TECH report invalid {uuid4().hex[:6]}",
        "status_code": "SUBMITTED",
        "tech": {
            "tech_subtype_code": "DAILY_REPORT",
        },
    }

    res = client.post("/api/v1/comm-items/create", json=payload, headers=headers)
    assert res.status_code == 400, res.text
