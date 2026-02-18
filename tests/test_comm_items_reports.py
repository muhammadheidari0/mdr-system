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
        code = f"RPT{uuid4().hex[:4].upper()}"
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
        code = f"RP{uuid4().hex[:3].upper()}"
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
        code = f"RORG{uuid4().hex[:4].upper()}"
        res = client.post(
            "/api/v1/settings/organizations/upsert",
            json={"code": code, "name": f"Org {code}", "org_type": "contractor", "is_active": True},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        org_id = int(res.json().get("id") or 0)
    else:
        org_id = int(orgs[0].get("id") or 0)

    return project_code, discipline_code, org_id


def test_comm_items_reports_return_expected_candidates_and_cycles() -> None:
    headers = _admin_headers()
    project_code, discipline_code, org_id = _ensure_context(headers)

    overdue_rfi_payload = {
        "item_type": "RFI",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"RFI overdue {uuid4().hex[:6]}",
        "status_code": "SUBMITTED",
        "recipient_org_id": org_id,
        "response_due_date": (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%dT00:00:00"),
        "rfi": {
            "question_text": "Please clarify this overdue item request to validate report behavior.",
        },
    }
    overdue_res = client.post("/api/v1/comm-items/create", json=overdue_rfi_payload, headers=headers)
    assert overdue_res.status_code == 200, overdue_res.text

    impact_tech_payload = {
        "item_type": "TECH",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"TECH impact {uuid4().hex[:6]}",
        "status_code": "DRAFT",
        "potential_impact_cost": True,
        "tech": {
            "tech_subtype_code": "INSTRUCTION",
            "document_no": f"DOC-{uuid4().hex[:4].upper()}",
            "revision": "A",
        },
    }
    impact_res = client.post("/api/v1/comm-items/create", json=impact_tech_payload, headers=headers)
    assert impact_res.status_code == 200, impact_res.text

    answered_rfi_payload = {
        "item_type": "RFI",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"RFI answered {uuid4().hex[:6]}",
        "status_code": "ANSWERED",
        "recipient_org_id": org_id,
        "response_due_date": (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00"),
        "rfi": {
            "question_text": "Cycle time answered request with enough details for report.",
            "answer_text": "Consultant response is issued.",
            "answered_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        },
    }
    answered_res = client.post("/api/v1/comm-items/create", json=answered_rfi_payload, headers=headers)
    assert answered_res.status_code == 200, answered_res.text

    closed_ncr_payload = {
        "item_type": "NCR",
        "project_code": project_code,
        "discipline_code": discipline_code,
        "title": f"NCR closed {uuid4().hex[:6]}",
        "status_code": "CLOSED",
        "ncr": {
            "kind": "NCR",
            "severity": "MINOR",
            "nonconformance_text": "Closed NCR sample row for cycle-time report validation.",
            "verification_note": "Verified and closed.",
            "verified_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        },
    }
    closed_ncr_res = client.post("/api/v1/comm-items/create", json=closed_ncr_payload, headers=headers)
    assert closed_ncr_res.status_code == 200, closed_ncr_res.text

    aging_res = client.get(
        f"/api/v1/comm-items/reports/aging?project_code={project_code}&discipline_code={discipline_code}",
        headers=headers,
    )
    assert aging_res.status_code == 200, aging_res.text
    aging_body = aging_res.json()
    assert aging_body.get("ok") is True
    assert int(aging_body.get("summary", {}).get("overdue", 0)) >= 1

    impact_res = client.get(
        f"/api/v1/comm-items/reports/impact-signals?project_code={project_code}&discipline_code={discipline_code}",
        headers=headers,
    )
    assert impact_res.status_code == 200, impact_res.text
    impact_body = impact_res.json()
    assert impact_body.get("ok") is True
    assert int(impact_body.get("count", 0)) >= 1

    legacy_claim_res = client.get(
        f"/api/v1/comm-items/reports/claim-candidates?project_code={project_code}&discipline_code={discipline_code}",
        headers=headers,
    )
    assert legacy_claim_res.status_code == 200, legacy_claim_res.text
    legacy_claim_body = legacy_claim_res.json()
    assert int(legacy_claim_body.get("count", 0)) == int(impact_body.get("count", 0))

    cycle_res = client.get(
        f"/api/v1/comm-items/reports/cycle-time?project_code={project_code}&discipline_code={discipline_code}",
        headers=headers,
    )
    assert cycle_res.status_code == 200, cycle_res.text
    cycle_body = cycle_res.json()
    assert cycle_body.get("ok") is True
    assert int(cycle_body.get("rfi_answered", {}).get("count", 0)) >= 1
    assert int(cycle_body.get("ncr_closed", {}).get("count", 0)) >= 1
