from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import SiteLog
from app.db.session import SessionLocal
from app.main import app
from app.services.bim_revit_security import (
    build_signature_canonical,
    compute_body_sha256,
    compute_plugin_signature,
)
from app.services.storage_policy import get_bim_revit_integration, set_bim_revit_integration
from tests.auth_helpers import get_auth_headers
from tests.site_logs_helpers import ensure_org, ensure_project_discipline


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _create_viewer_headers(admin_headers: dict[str, str]) -> dict[str, str]:
    project_code, discipline_code = ensure_project_discipline(client, admin_headers)
    org_id = ensure_org(client, admin_headers, org_type="consultant", code_prefix="BIMVIEW")
    assert org_id > 0

    email = f"bim_viewer_{uuid4().hex[:8]}@mdr.local"
    password = f"Pwd!{uuid4().hex[:10]}"
    create_res = client.post(
        "/api/v1/users/",
        json={
            "email": email,
            "password": password,
            "full_name": "BIM Viewer",
            "role": "viewer",
            "organization_id": org_id,
            "organization_role": "viewer",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert create_res.status_code == 200, create_res.text

    login_res = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert login_res.status_code == 200, login_res.text
    token = str(login_res.json().get("access_token") or "").strip()
    assert token

    # Viewer permission check does not need explicit scope seed because request should
    # fail on permission before scope is evaluated.
    _ = project_code, discipline_code
    return {"Authorization": f"Bearer {token}"}


def _read_bim_revit_raw() -> dict:
    with SessionLocal() as db:
        return get_bim_revit_integration(db)


def _restore_bim_revit_raw(payload: dict) -> None:
    with SessionLocal() as db:
        set_bim_revit_integration(db, payload)
        db.commit()


def _signed_plugin_headers(
    *,
    key_id: str,
    secret: str,
    body: bytes,
    base_headers: dict[str, str],
) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    nonce = uuid4().hex
    canonical = build_signature_canonical(
        method="POST",
        path="/api/v1/bim/edms/inbox/publish-batch",
        timestamp=timestamp,
        nonce=nonce,
        body_sha256=compute_body_sha256(body),
    )
    signature = compute_plugin_signature(secret=secret, canonical=canonical)
    headers = dict(base_headers)
    headers["content-type"] = "application/json"
    headers["X-MDR-Plugin-KeyId"] = key_id
    headers["X-MDR-Plugin-Timestamp"] = timestamp
    headers["X-MDR-Plugin-Nonce"] = nonce
    headers["X-MDR-Plugin-Signature"] = signature
    return headers


def _create_verified_log(
    headers: dict[str, str],
    *,
    project_code: str,
    discipline_code: str,
) -> int:
    create_res = client.post(
        "/api/v1/site-logs/create",
        json={
            "log_type": "DAILY",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "log_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
            "summary": "BIM sync source",
            "manpower_rows": [
                {
                    "role_code": "WORKER",
                    "role_label": "Worker",
                    "claimed_count": 4,
                    "claimed_hours": 8.0,
                    "sort_order": 0,
                }
            ],
            "equipment_rows": [],
            "activity_rows": [],
        },
        headers=headers,
    )
    assert create_res.status_code == 200, create_res.text
    log_id = int(create_res.json().get("data", {}).get("id") or 0)
    assert log_id > 0

    submit_res = client.post(f"/api/v1/site-logs/{log_id}/submit", json={"note": "submit"}, headers=headers)
    assert submit_res.status_code == 200, submit_res.text

    verify_res = client.post(
        f"/api/v1/site-logs/{log_id}/verify",
        json={
            "manpower_rows": [
                {
                    "sort_order": 0,
                    "verified_count": 3,
                    "verified_hours": 7.5,
                }
            ],
            "note": "verified",
        },
        headers=headers,
    )
    assert verify_res.status_code == 200, verify_res.text
    return log_id


def test_bim_auth_and_permission_guards() -> None:
    unauthorized = client.get("/api/v1/bim/config")
    assert unauthorized.status_code in (401, 403), unauthorized.text

    admin = _admin_headers()
    viewer = _create_viewer_headers(admin)

    project_code, _ = ensure_project_discipline(client, admin)
    publish_res = client.post(
        "/api/v1/bim/edms/publish-batch",
        json={
            "project_code": project_code,
            "items": [
                {
                    "item_index": 0,
                    "sheet_unique_id": f"SHEET-{uuid4().hex[:8]}",
                    "requested_revision": "A",
                    "file_sha256": "a" * 64,
                }
            ],
        },
        headers=viewer,
    )
    assert publish_res.status_code == 403, publish_res.text


def test_bim_publish_idempotency_and_conflict_rules() -> None:
    admin = _admin_headers()
    project_code, _ = ensure_project_discipline(client, admin)

    sheet_uid = f"SHEET-{uuid4().hex[:8]}"
    subject = f"BIM-{uuid4().hex[:6]}"
    base_item = {
        "item_index": 0,
        "sheet_unique_id": sheet_uid,
        "sheet_number": "A-101",
        "sheet_name": "General Plan",
        "requested_revision": "A",
        "status_code": "IFA",
        "metadata": {
            "mdr_code": "E",
            "phase": "X",
            "discipline": "GN",
            "package": "00",
            "block": "G",
            "level": "GEN",
            "subject": subject,
        },
        "file_sha256": "a" * 64,
    }

    run1 = client.post(
        "/api/v1/bim/edms/publish-batch",
        json={
            "project_code": project_code,
            "items": [base_item],
        },
        headers=admin,
    )
    assert run1.status_code == 200, run1.text
    body1 = run1.json()
    assert body1.get("summary", {}).get("success_count") == 1
    assert body1.get("items", [])[0].get("state") == "completed"

    conflict_item = dict(base_item)
    conflict_item["item_index"] = 1
    conflict_item["file_sha256"] = "b" * 64

    run2 = client.post(
        "/api/v1/bim/edms/publish-batch",
        json={
            "project_code": project_code,
            "items": [base_item, conflict_item],
        },
        headers=admin,
    )
    assert run2.status_code == 200, run2.text
    body2 = run2.json()
    summary2 = body2.get("summary", {})
    assert summary2.get("requested_count") == 2
    assert summary2.get("duplicate_count") == 1
    assert summary2.get("failed_count") == 1

    items2 = body2.get("items", [])
    assert len(items2) == 2
    assert any(item.get("state") == "duplicate" for item in items2)
    assert any(item.get("error_code") == "conflict_revision_content" for item in items2)

    run_id = str(body2.get("run_id") or "")
    run_items = client.get(f"/api/v1/bim/edms/runs/{run_id}/items", headers=admin)
    assert run_items.status_code == 200, run_items.text
    assert len(run_items.json().get("items", [])) == 2


def test_bim_publish_multipart_with_pdf_upload() -> None:
    admin = _admin_headers()
    project_code, _ = ensure_project_discipline(client, admin)

    sheet_uid = f"SHEET-{uuid4().hex[:8]}"
    subject = f"BIMMP-{uuid4().hex[:6]}"
    items = [
        {
            "item_index": 0,
            "sheet_unique_id": sheet_uid,
            "sheet_number": "A-102",
            "sheet_name": "General Plan Multipart",
            "requested_revision": "A",
            "status_code": "IFA",
            "include_native": False,
            "metadata": {
                "mdr_code": "E",
                "phase": "X",
                "discipline": "GN",
                "package": "00",
                "block": "G",
                "level": "GEN",
                "subject": subject,
            },
        }
    ]
    files_manifest = [
        {
            "item_index": 0,
            "sheet_unique_id": sheet_uid,
            "pdf_file_name": "sheet_0.pdf",
        }
    ]

    res = client.post(
        "/api/v1/bim/edms/publish-batch",
        data={
            "project_code": project_code,
            "run_client_id": f"run-{uuid4().hex[:8]}",
            "items_json": json.dumps(items),
            "files_manifest": json.dumps(files_manifest),
        },
        files=[
            ("files", ("sheet_0.pdf", b"%PDF-1.4 multipart sample", "application/pdf")),
        ],
        headers=admin,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("summary", {}).get("requested_count") == 1
    assert body.get("summary", {}).get("success_count") == 1
    assert body.get("items", [])[0].get("state") == "completed"
    assert body.get("items", [])[0].get("pdf_file_id") is not None


def test_bim_inbox_publish_signature_and_inbox_endpoints() -> None:
    admin = _admin_headers()
    project_code, _ = ensure_project_discipline(client, admin)
    before = _read_bim_revit_raw()
    key_id = f"BIMKEY-{uuid4().hex[:8]}".upper()
    secret = f"bim-secret-{uuid4().hex[:16]}"
    try:
        save_cfg = client.post(
            "/api/v1/settings/bim-revit",
            json={
                "enabled": True,
                "require_plugin_signature": True,
                "plugin_key_id": key_id,
                "plugin_secret": secret,
                "api_endpoint_url": "https://mdr.example.com/api/v1/bim/edms/inbox/publish-batch",
            },
            headers=admin,
        )
        assert save_cfg.status_code == 200, save_cfg.text

        payload = {
            "project_code": project_code,
            "run_client_id": f"inbox-{uuid4().hex[:8]}",
            "items": [
                {
                    "item_index": 0,
                    "sheet_unique_id": f"SHEET-{uuid4().hex[:8]}",
                    "sheet_number": "A-301",
                    "sheet_name": "Inbox Signed",
                    "requested_revision": "A",
                    "status_code": "IFA",
                    "file_sha256": "c" * 64,
                }
            ],
        }
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        signed_headers = _signed_plugin_headers(
            key_id=key_id,
            secret=secret,
            body=body,
            base_headers=admin,
        )

        publish_res = client.post(
            "/api/v1/bim/edms/inbox/publish-batch",
            content=body,
            headers=signed_headers,
        )
        assert publish_res.status_code == 200, publish_res.text
        publish_body = publish_res.json()
        run_id = str(publish_body.get("run_id") or "")
        assert run_id
        assert publish_body.get("status") in {"staged", "staged_with_errors"}

        bad_headers = dict(signed_headers)
        bad_headers["X-MDR-Plugin-Nonce"] = uuid4().hex
        bad_headers["X-MDR-Plugin-Signature"] = "deadbeef"
        bad_res = client.post(
            "/api/v1/bim/edms/inbox/publish-batch",
            content=body,
            headers=bad_headers,
        )
        assert bad_res.status_code == 403, bad_res.text

        runs_res = client.get(
            "/api/v1/bim/edms/inbox/runs",
            params={"project_code": project_code},
            headers=admin,
        )
        assert runs_res.status_code == 200, runs_res.text
        runs = runs_res.json().get("items", [])
        assert any(str(row.get("run_id") or "") == run_id for row in runs)

        run_res = client.get(f"/api/v1/bim/edms/inbox/runs/{run_id}", headers=admin)
        assert run_res.status_code == 200, run_res.text
        assert str(run_res.json().get("run_id") or "") == run_id

        items_res = client.get(f"/api/v1/bim/edms/inbox/runs/{run_id}/items", headers=admin)
        assert items_res.status_code == 200, items_res.text
        run_items = items_res.json().get("items", [])
        assert len(run_items) == 1
    finally:
        _restore_bim_revit_raw(before)


def test_bim_inbox_approve_reject_permissions_and_flow() -> None:
    admin = _admin_headers()
    viewer = _create_viewer_headers(admin)
    project_code, _ = ensure_project_discipline(client, admin)
    before = _read_bim_revit_raw()
    try:
        save_cfg = client.post(
            "/api/v1/settings/bim-revit",
            json={
                "enabled": True,
                "require_plugin_signature": False,
                "plugin_key_id": "",
                "plugin_secret": "",
                "api_endpoint_url": "https://mdr.example.com/api/v1/bim/edms/inbox/publish-batch",
            },
            headers=admin,
        )
        assert save_cfg.status_code == 200, save_cfg.text

        approve_sheet_uid = f"SHEET-{uuid4().hex[:8]}"
        approve_items = [
            {
                "item_index": 0,
                "sheet_unique_id": approve_sheet_uid,
                "sheet_number": "A-401",
                "sheet_name": "Approve Candidate",
                "requested_revision": "A",
                "status_code": "IFA",
                "metadata": {
                    "mdr_code": "E",
                    "phase": "X",
                    "discipline": "GN",
                    "package": "00",
                    "block": "G",
                    "level": "GEN",
                    "subject": f"INBOX-APPROVE-{uuid4().hex[:6]}",
                },
            }
        ]
        approve_manifest = [
            {
                "item_index": 0,
                "sheet_unique_id": approve_sheet_uid,
                "pdf_file_name": "approve_0.pdf",
            }
        ]
        publish_res = client.post(
            "/api/v1/bim/edms/inbox/publish-batch",
            data={
                "project_code": project_code,
                "run_client_id": f"inbox-approve-{uuid4().hex[:8]}",
                "items_json": json.dumps(approve_items),
                "files_manifest": json.dumps(approve_manifest),
            },
            files=[
                ("files", ("approve_0.pdf", b"%PDF-1.4 inbox approve sample", "application/pdf")),
            ],
            headers=admin,
        )
        assert publish_res.status_code == 200, publish_res.text
        run_id = str(publish_res.json().get("run_id") or "")
        assert run_id

        viewer_approve = client.post(f"/api/v1/bim/edms/inbox/runs/{run_id}/approve", headers=viewer)
        assert viewer_approve.status_code == 403, viewer_approve.text

        approve_res = client.post(f"/api/v1/bim/edms/inbox/runs/{run_id}/approve", headers=admin)
        assert approve_res.status_code == 200, approve_res.text
        approve_body = approve_res.json()
        assert approve_body.get("status") == "approved"
        assert int(approve_body.get("failed_count") or 0) == 0

        publish_res_2 = client.post(
            "/api/v1/bim/edms/inbox/publish-batch",
            json={
                "project_code": project_code,
                "run_client_id": f"inbox-reject-{uuid4().hex[:8]}",
                "items": [
                    {
                        "item_index": 0,
                        "sheet_unique_id": f"SHEET-{uuid4().hex[:8]}",
                        "sheet_number": "A-402",
                        "sheet_name": "Reject Candidate",
                        "requested_revision": "A",
                        "status_code": "IFA",
                        "file_sha256": "e" * 64,
                    }
                ],
            },
            headers=admin,
        )
        assert publish_res_2.status_code == 200, publish_res_2.text
        run_id_2 = str(publish_res_2.json().get("run_id") or "")
        assert run_id_2

        reject_res = client.post(
            f"/api/v1/bim/edms/inbox/runs/{run_id_2}/reject",
            json={"reason": "manual validation failed"},
            headers=admin,
        )
        assert reject_res.status_code == 200, reject_res.text
        assert reject_res.json().get("status") == "rejected"

        approve_rejected = client.post(f"/api/v1/bim/edms/inbox/runs/{run_id_2}/approve", headers=admin)
        assert approve_rejected.status_code == 409, approve_rejected.text
    finally:
        _restore_bim_revit_raw(before)


def test_bim_schedule_ingest_approve_reject_workflow() -> None:
    admin = _admin_headers()
    project_code, _ = ensure_project_discipline(client, admin)

    ingest = client.post(
        "/api/v1/bim/schedules/ingest",
        json={
            "project_code": project_code,
            "profile_code": "MTO",
            "model_guid": f"model-{uuid4().hex[:8]}",
            "schema_version": "v1",
            "rows": [
                {"row_no": 1, "element_key": "EL-001", "values": {"quantity": 12.5}},
                {"row_no": 2, "values": {"quantity": 4.0}},
            ],
        },
        headers=admin,
    )
    assert ingest.status_code == 200, ingest.text
    ingest_body = ingest.json()
    run_id = str(ingest_body.get("run_id") or "")
    summary = ingest_body.get("validation_summary", {})
    assert summary.get("total_rows") == 2
    assert summary.get("valid_rows") == 1
    assert summary.get("invalid_rows") == 1

    approve = client.post(f"/api/v1/bim/schedules/runs/{run_id}/approve", headers=admin)
    assert approve.status_code == 200, approve.text
    approve_body = approve.json()
    assert approve_body.get("merged_rows") == 1
    assert approve_body.get("status") == "APPROVED"

    reject_after_approve = client.post(
        f"/api/v1/bim/schedules/runs/{run_id}/reject",
        json={"reason": "late"},
        headers=admin,
    )
    assert reject_after_approve.status_code == 409, reject_after_approve.text

    ingest2 = client.post(
        "/api/v1/bim/schedules/ingest",
        json={
            "project_code": project_code,
            "profile_code": "EQUIPMENT",
            "model_guid": f"model-{uuid4().hex[:8]}",
            "schema_version": "v1",
            "rows": [
                {
                    "row_no": 1,
                    "equipment_key": "EQ-001",
                    "values": {"verified_hours": 5},
                }
            ],
        },
        headers=admin,
    )
    assert ingest2.status_code == 200, ingest2.text
    run2 = str(ingest2.json().get("run_id") or "")

    reject = client.post(
        f"/api/v1/bim/schedules/runs/{run2}/reject",
        json={"reason": "invalid mapping"},
        headers=admin,
    )
    assert reject.status_code == 200, reject.text
    assert reject.json().get("status") == "REJECTED"


def test_bim_writeback_manifest_pull_ack_and_delete_detection() -> None:
    admin = _admin_headers()
    project_code, discipline_code = ensure_project_discipline(client, admin)
    log_id = _create_verified_log(admin, project_code=project_code, discipline_code=discipline_code)
    model_guid = f"model-{uuid4().hex[:8]}"

    manifest = client.get(
        "/api/v1/bim/site-logs/revit/manifest",
        params={
            "project_code": project_code,
            "client_model_guid": model_guid,
        },
        headers=admin,
    )
    assert manifest.status_code == 200, manifest.text
    manifest_body = manifest.json()
    changes = manifest_body.get("changes", [])
    assert any(int(row.get("log_id") or 0) == log_id and row.get("operation") == "upsert" for row in changes)

    pull = client.post(
        "/api/v1/bim/site-logs/revit/pull",
        json={
            "project_code": project_code,
            "client_model_guid": model_guid,
            "log_ids": [log_id],
        },
        headers=admin,
    )
    assert pull.status_code == 200, pull.text
    pull_body = pull.json()
    run_id = str(pull_body.get("run_id") or "")
    assert run_id

    applied = (
        len(pull_body.get("manpower_rows", []))
        + len(pull_body.get("equipment_rows", []))
        + len(pull_body.get("activity_rows", []))
    )
    ack = client.post(
        "/api/v1/bim/site-logs/revit/ack",
        json={
            "run_id": run_id,
            "applied_count": applied,
            "failed_count": 0,
            "errors": [],
        },
        headers=admin,
    )
    assert ack.status_code == 200, ack.text
    assert ack.json().get("ok") is True

    with SessionLocal() as db:
        row = db.query(SiteLog).filter(SiteLog.id == log_id).first()
        assert row is not None
        row.status_code = "DRAFT"
        row.updated_at = datetime.utcnow()
        db.commit()

    manifest_delete = client.get(
        "/api/v1/bim/site-logs/revit/manifest",
        params={
            "project_code": project_code,
            "client_model_guid": model_guid,
        },
        headers=admin,
    )
    assert manifest_delete.status_code == 200, manifest_delete.text
    changes2 = manifest_delete.json().get("changes", [])
    assert any(int(row.get("log_id") or 0) == log_id and row.get("operation") == "delete" for row in changes2)
