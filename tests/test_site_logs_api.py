from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.models import Block, CommItem, OrganizationContract, PermitQcPermit, TechDetail
from app.db.session import SessionLocal
from app.main import app
from tests.site_logs_helpers import (
    admin_headers,
    create_scoped_user_and_login,
    ensure_project_discipline,
)


client = TestClient(app)


def _create_draft(
    headers: dict[str, str],
    *,
    project_code: str,
    discipline_code: str | None,
    organization_id: int,
    organization_contract_id: int | None = None,
    include_rows: bool = True,
    work_status: str = "ACTIVE",
) -> dict[str, object]:
    payload = {
        "log_type": "DAILY",
        "project_code": project_code,
        "organization_id": int(organization_id),
        "organization_contract_id": organization_contract_id,
        "log_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
        "work_status": work_status,
        "shift": "DAY",
        "weather": "CLEAR",
        "current_work_summary": "Current workshop summary from api test",
        "next_plan_summary": "Next plan from api test",
        "qc_open_punch_count": 2,
        "qc_summary_note": "QC follow-up summary from api test",
        "manpower_rows": (
            [{"role_code": "FOREMAN", "role_label": "Foreman", "claimed_count": 4, "claimed_hours": 8.0, "sort_order": 0}]
            if include_rows
            else []
        ),
        "equipment_rows": (
            [
                {
                    "equipment_code": "CRN",
                    "equipment_label": "Crane",
                    "work_location": "Zone A",
                    "claimed_count": 2,
                    "claimed_status": "ACTIVE",
                    "claimed_hours": 5.5,
                    "sort_order": 0,
                }
            ]
            if include_rows
            else []
        ),
        "activity_rows": (
            [
                {
                    "activity_code": "CV-101",
                    "activity_title": "Foundation concrete",
                    "location": "B-Block",
                    "unit": "Ton",
                    "personnel_count": 12,
                    "today_quantity": 4.8,
                    "cumulative_quantity": 18.2,
                    "activity_status": "در حال انجام",
                    "stop_reason": None,
                    "note": "طبق برنامه",
                    "sort_order": 0,
                }
            ]
            if include_rows
            else []
        ),
        "material_rows": (
            [
                {
                    "material_code": "MT-22",
                    "title": "A3 Size 20 rebar",
                    "consumption_location": "Slab B",
                    "unit": "Ton",
                    "incoming_quantity": 6,
                    "consumed_quantity": 4.8,
                    "cumulative_quantity": 18.2,
                    "note": "Warehouse B delivery",
                    "sort_order": 0,
                }
            ]
            if include_rows
            else []
        ),
        "issue_rows": (
            [
                {
                    "issue_type": "MATERIAL",
                    "description": "Delay in slab formwork delivery",
                    "responsible_party": "Contractor",
                    "due_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
                    "status": "OPEN",
                    "note": "Follow-up with procurement",
                    "sort_order": 0,
                }
            ]
            if include_rows
            else []
        ),
        "attachment_rows": [],
    }
    if discipline_code:
        payload["discipline_code"] = discipline_code
    res = client.post("/api/v1/site-logs/create", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    data = body.get("data", {})
    assert str(data.get("status_code")) == "DRAFT"
    assert str(data.get("log_no", "")).startswith(f"{project_code}-SLOG-")
    assert data.get("discipline_code") in (discipline_code, None, "")
    assert str(data.get("shift") or "") == "DAY"
    assert str(data.get("work_status") or "") == work_status
    assert str(data.get("shift_label") or "") in {"روز", "DAY"}
    assert str(data.get("weather") or "") == "CLEAR"
    assert str(data.get("weather_label") or "") in {"صاف", "CLEAR"}
    assert str(data.get("current_work_summary") or "").startswith("Current workshop")
    assert str(data.get("next_plan_summary") or "").startswith("Next plan")
    assert int(data.get("qc_open_punch_count") or 0) == 2
    assert str(data.get("qc_summary_note") or "").startswith("QC follow-up")
    if include_rows:
        equipment_rows = data.get("equipment_rows") or []
        assert len(equipment_rows) == 1
        assert int(equipment_rows[0].get("claimed_count") or 0) == 2
        assert equipment_rows[0].get("work_location") == "Zone A"
        material_rows = data.get("material_rows") or []
        assert len(material_rows) == 1
        assert material_rows[0].get("consumption_location") == "Slab B"
        assert len(data.get("issue_rows") or []) == 1
    return data


def _ensure_contract(project_code: str, organization_id: int) -> OrganizationContract:
    with SessionLocal() as db:
        block = Block(
            project_code=project_code,
            code=f"B{uuid4().hex[:4].upper()}",
            name_e="Workshop Block",
            name_p="Workshop Block",
            sort_order=10,
            is_active=True,
        )
        db.add(block)
        db.flush()
        contract = OrganizationContract(
            organization_id=int(organization_id),
            contract_number=f"CN-{uuid4().hex[:4].upper()}",
            subject=f"Workshop package {uuid4().hex[:4]}",
            block_id=int(block.id),
            sort_order=10,
        )
        db.add(contract)
        db.commit()
        db.refresh(contract)
        db.refresh(block)
        return contract


def _seed_qc_sources(
    *,
    project_code: str,
    discipline_code: str,
    organization_id: int,
    log_date: datetime,
) -> None:
    with SessionLocal() as db:
        db.add(
            PermitQcPermit(
                permit_no=f"PERMIT-{uuid4().hex[:6].upper()}",
                permit_date=log_date,
                title="Permit QC for site log snapshot",
                status_code="SUBMITTED",
                project_code=project_code,
                discipline_code=discipline_code,
                organization_id=int(organization_id),
                contractor_org_id=int(organization_id),
            )
        )
        tech_item = CommItem(
            item_no=f"TECH-{uuid4().hex[:6].upper()}",
            item_type="TECH",
            project_code=project_code,
            discipline_code=discipline_code,
            organization_id=int(organization_id),
            contractor_org_id=int(organization_id),
            title="Inspection request sample",
            status_code="OPEN",
            priority="NORMAL",
            created_at=log_date,
            updated_at=log_date,
        )
        tech_item.tech_detail = TechDetail(tech_subtype_code="IR")
        db.add(tech_item)
        db.add(
            CommItem(
                item_no=f"NCR-{uuid4().hex[:6].upper()}",
                item_type="NCR",
                project_code=project_code,
                discipline_code=discipline_code,
                organization_id=int(organization_id),
                contractor_org_id=int(organization_id),
                title="Open NCR sample",
                status_code="ISSUED",
                priority="NORMAL",
                created_at=log_date,
                updated_at=log_date,
            )
        )
        db.commit()


def test_site_log_attachments_use_optional_site_log_storage_path(monkeypatch, tmp_path: Path) -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)
    contractor = create_scoped_user_and_login(
        client,
        admin,
        org_type="contractor",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="site_storage",
        organization_role="manager",
    )
    contractor_headers = contractor["headers"]  # type: ignore[assignment]
    organization_id = int(contractor.get("organization_id") or 0)

    paths_before = client.get("/api/v1/settings/storage-paths", headers=admin)
    assert paths_before.status_code == 200, paths_before.text
    paths_before_body = paths_before.json()
    integrations_before = client.get("/api/v1/settings/storage-integrations", headers=admin)
    assert integrations_before.status_code == 200, integrations_before.text
    integrations_before_body = integrations_before.json().get("integrations") or {}

    storage_root = (tmp_path / "storage").resolve()
    mdr_path = (storage_root / "technical").resolve()
    corr_path = (storage_root / "correspondence").resolve()
    site_log_path = (storage_root / "site_logs_explicit").resolve()

    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", str(storage_root))
    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", True)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", False)

    try:
        force_local = client.post(
            "/api/v1/settings/storage-integrations",
            json={"primary": {"provider": "local"}, "mirror": {"provider": "none"}},
            headers=admin,
        )
        assert force_local.status_code == 200, force_local.text
        save_paths = client.post(
            "/api/v1/settings/storage-paths",
            json={
                "mdr_storage_path": str(mdr_path),
                "correspondence_storage_path": str(corr_path),
                "site_log_storage_path": str(site_log_path),
            },
            headers=admin,
        )
        assert save_paths.status_code == 200, save_paths.text

        draft = _create_draft(
            contractor_headers,  # type: ignore[arg-type]
            project_code=project_code,
            discipline_code=None,
            organization_id=organization_id,
            include_rows=True,
        )
        draft_id = int(draft.get("id") or 0)
        upload_res = client.post(
            f"/api/v1/site-logs/{draft_id}/attachments",
            headers=contractor_headers,  # type: ignore[arg-type]
            files={"file": ("site-log-storage.txt", BytesIO(b"site log storage"), "text/plain")},
            data={"section_code": "REPORT_ATTACHMENT", "file_kind": "attachment"},
        )
        assert upload_res.status_code == 200, upload_res.text
        stored_path = Path(str(upload_res.json().get("data", {}).get("stored_path") or "")).resolve()
        assert str(stored_path).lower().startswith(str(site_log_path).lower())
        assert "site_logs" in {part.lower() for part in stored_path.parts}
    finally:
        monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", False)
        monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", False)
        monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", "")
        restore_paths = client.post(
            "/api/v1/settings/storage-paths",
            json={
                "mdr_storage_path": paths_before_body.get("mdr_storage_path") or "./files/technical",
                "correspondence_storage_path": paths_before_body.get("correspondence_storage_path")
                or "./files/correspondence",
                "site_log_storage_path": paths_before_body.get("site_log_storage_path") or "",
            },
            headers=admin,
        )
        assert restore_paths.status_code == 200, restore_paths.text
        restore_integrations = client.post(
            "/api/v1/settings/storage-integrations",
            json={
                "primary": {"provider": str((integrations_before_body.get("primary") or {}).get("provider") or "local")},
                "mirror": {"provider": str((integrations_before_body.get("mirror") or {}).get("provider") or "none")},
            },
            headers=admin,
        )
        assert restore_integrations.status_code == 200, restore_integrations.text


def test_site_logs_api_core_workflow_and_guards() -> None:
    admin = admin_headers(client)
    project_code, discipline_code = ensure_project_discipline(client, admin)

    contractor = create_scoped_user_and_login(
        client,
        admin,
        org_type="contractor",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="site_contractor",
        organization_role="manager",
    )
    consultant = create_scoped_user_and_login(
        client,
        admin,
        org_type="consultant",
        project_code=project_code,
        discipline_code=discipline_code,
        email_prefix="site_consultant",
        organization_role="manager",
    )

    contractor_headers = contractor["headers"]  # type: ignore[assignment]
    consultant_headers = consultant["headers"]  # type: ignore[assignment]
    organization_id = int(contractor.get("organization_id") or 0)
    log_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    contract = _ensure_contract(project_code, organization_id)
    _seed_qc_sources(
        project_code=project_code,
        discipline_code=discipline_code,
        organization_id=organization_id,
        log_date=log_date,
    )

    draft = _create_draft(
        contractor_headers,  # type: ignore[arg-type]
        project_code=project_code,
        discipline_code=None,
        organization_id=organization_id,
        organization_contract_id=int(contract.id),
        include_rows=True,
    )
    draft_id = int(draft.get("id") or 0)
    assert draft_id > 0
    assert int(draft.get("organization_contract_id") or 0) == int(contract.id)
    assert str(draft.get("contract_number") or "") == str(contract.contract_number)
    assert str(draft.get("contract_subject") or "") == str(contract.subject)
    assert int(draft.get("qc_test_count") or 0) >= 1
    assert int(draft.get("qc_inspection_count") or 0) >= 1
    assert int(draft.get("qc_open_ncr_count") or 0) >= 1

    get_draft = client.get(f"/api/v1/site-logs/{draft_id}", headers=contractor_headers)  # type: ignore[arg-type]
    assert get_draft.status_code == 200, get_draft.text
    draft_data = get_draft.json().get("data", {})
    assert draft_data.get("discipline_code") in (None, "")
    assert draft_data.get("shift") == "DAY"
    assert int(draft_data.get("organization_contract_id") or 0) == int(contract.id)
    assert draft_data.get("contract_number") == contract.contract_number
    assert draft_data.get("contract_subject") == contract.subject
    assert draft_data.get("activity_rows", [{}])[0].get("today_quantity") == 4.8
    assert draft_data.get("activity_rows", [{}])[0].get("personnel_count") == 12
    assert draft_data.get("material_rows", [{}])[0].get("material_code") == "MT-22"
    assert draft_data.get("material_rows", [{}])[0].get("title") == "A3 Size 20 rebar"
    assert draft_data.get("issue_rows", [{}])[0].get("issue_type") == "MATERIAL"
    assert int(draft_data.get("qc_test_count") or 0) >= 1
    manpower_row_id = int(draft_data.get("manpower_rows", [{}])[0].get("id") or 0)
    assert manpower_row_id > 0

    runtime_catalog = client.get("/api/v1/site-logs/catalog", headers=contractor_headers)  # type: ignore[arg-type]
    assert runtime_catalog.status_code == 200, runtime_catalog.text
    material_catalog = runtime_catalog.json().get("material_catalog") or []
    assert any(item.get("code") == "MT-22" and item.get("label") == "A3 Size 20 rebar" and item.get("unit") == "Ton" for item in material_catalog)

    pdf_res = client.get(f"/api/v1/site-logs/{draft_id}/pdf", headers=contractor_headers)  # type: ignore[arg-type]
    assert pdf_res.status_code == 200, pdf_res.text
    assert pdf_res.headers.get("content-type", "").startswith("application/pdf")
    assert "attachment" in pdf_res.headers.get("content-disposition", "").lower()
    assert str(draft.get("log_no") or "") in pdf_res.headers.get("content-disposition", "")
    assert pdf_res.content.startswith(b"%PDF")

    qc_snapshot_res = client.get(
        f"/api/v1/site-logs/qc-snapshot?project_code={project_code}&organization_id={organization_id}&log_date={log_date.strftime('%Y-%m-%dT00:00:00')}",
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert qc_snapshot_res.status_code == 200, qc_snapshot_res.text
    qc_snapshot_body = qc_snapshot_res.json()
    assert int(qc_snapshot_body.get("qc_test_count") or 0) >= 1
    assert int(qc_snapshot_body.get("qc_inspection_count") or 0) >= 1
    assert int(qc_snapshot_body.get("qc_open_ncr_count") or 0) >= 1

    list_res = client.get("/api/v1/site-logs/list", headers=contractor_headers)  # type: ignore[arg-type]
    assert list_res.status_code == 200, list_res.text
    listed_ids = [int(item.get("id") or 0) for item in list_res.json().get("data", [])]
    assert draft_id in listed_ids

    draft_day = str(draft_data.get("log_date") or "")[:10]
    filtered_list_res = client.get(
        (
            "/api/v1/site-logs/list"
            f"?project_code={project_code}"
            f"&organization_id={organization_id}"
            f"&organization_contract_id={int(contract.id)}"
            "&work_status=ACTIVE"
            f"&log_date_from={draft_day}"
            f"&log_date_to={draft_day}"
        ),
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert filtered_list_res.status_code == 200, filtered_list_res.text
    filtered_rows = filtered_list_res.json().get("data", [])
    assert draft_id in [int(item.get("id") or 0) for item in filtered_rows]
    assert all(int(item.get("organization_id") or 0) == organization_id for item in filtered_rows)
    assert all(int(item.get("organization_contract_id") or 0) == int(contract.id) for item in filtered_rows)

    old_date_list_res = client.get(
        f"/api/v1/site-logs/list?project_code={project_code}&organization_id={organization_id}&log_date_from=1900-01-01&log_date_to=1900-01-01",
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert old_date_list_res.status_code == 200, old_date_list_res.text
    assert draft_id not in [int(item.get("id") or 0) for item in old_date_list_res.json().get("data", [])]

    upload_res = client.post(
        f"/api/v1/site-logs/{draft_id}/attachments",
        headers=contractor_headers,  # type: ignore[arg-type]
        files={"file": ("daily-note.txt", BytesIO(b"attachment body"), "text/plain")},
        data={"section_code": "GENERAL", "file_kind": "attachment"},
    )
    assert upload_res.status_code == 200, upload_res.text
    attachment_id = int(upload_res.json().get("data", {}).get("id") or 0)
    assert attachment_id > 0

    unsupported_preview = client.get(
        f"/api/v1/site-logs/attachments/{attachment_id}/preview",
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert unsupported_preview.status_code == 415, unsupported_preview.text

    pdf_attachment = client.post(
        f"/api/v1/site-logs/{draft_id}/attachments",
        headers=contractor_headers,  # type: ignore[arg-type]
        files={"file": ("daily-note.pdf", BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"), "application/pdf")},
        data={"section_code": "GENERAL", "file_kind": "attachment"},
    )
    assert pdf_attachment.status_code == 200, pdf_attachment.text
    pdf_attachment_id = int(pdf_attachment.json().get("data", {}).get("id") or 0)
    assert pdf_attachment_id > 0
    pdf_preview = client.get(
        f"/api/v1/site-logs/attachments/{pdf_attachment_id}/preview",
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert pdf_preview.status_code == 200, pdf_preview.text
    assert pdf_preview.headers.get("content-type", "").startswith("application/pdf")
    assert "inline" in pdf_preview.headers.get("content-disposition", "").lower()
    assert pdf_preview.content.startswith(b"%PDF")

    png_attachment = client.post(
        f"/api/v1/site-logs/{draft_id}/attachments",
        headers=contractor_headers,  # type: ignore[arg-type]
        files={
            "file": (
                "daily-photo.png",
                BytesIO(
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
                    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
                ),
                "image/png",
            )
        },
        data={"section_code": "GENERAL", "file_kind": "attachment"},
    )
    assert png_attachment.status_code == 200, png_attachment.text
    png_attachment_id = int(png_attachment.json().get("data", {}).get("id") or 0)
    assert png_attachment_id > 0
    png_preview = client.get(
        f"/api/v1/site-logs/attachments/{png_attachment_id}/preview",
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert png_preview.status_code == 200, png_preview.text
    assert png_preview.headers.get("content-type", "").startswith("image/png")
    assert png_preview.content.startswith(b"\x89PNG")

    manpower_row_file = client.post(
        f"/api/v1/site-logs/{draft_id}/attachments",
        headers=contractor_headers,  # type: ignore[arg-type]
        files={"file": ("manpower-photo.txt", BytesIO(b"manpower row file"), "text/plain")},
        data={"section_code": "MANPOWER", "file_kind": "attachment", "row_id": str(manpower_row_id), "note": "Foreman row"},
    )
    assert manpower_row_file.status_code == 200, manpower_row_file.text
    material_row_file = client.post(
        f"/api/v1/site-logs/{draft_id}/attachments",
        headers=contractor_headers,  # type: ignore[arg-type]
        files={"file": ("material-ticket.txt", BytesIO(b"material row file"), "text/plain")},
        data={"section_code": "MATERIAL", "file_kind": "attachment", "row_id": "1", "note": "Material row"},
    )
    assert material_row_file.status_code == 200, material_row_file.text

    get_with_row_files = client.get(f"/api/v1/site-logs/{draft_id}", headers=contractor_headers)  # type: ignore[arg-type]
    assert get_with_row_files.status_code == 200, get_with_row_files.text
    row_file_data = get_with_row_files.json().get("data", {})
    manpower_files = row_file_data.get("manpower_rows", [{}])[0].get("attachment_files") or []
    material_files = row_file_data.get("material_rows", [{}])[0].get("attachment_files") or []
    assert any(str(item.get("file_name") or "") == "manpower-photo.txt" for item in manpower_files)
    assert any(str(item.get("section_code") or "") == "MATERIAL" for item in material_files)

    preserve_row_update = client.put(
        f"/api/v1/site-logs/{draft_id}",
        json={
            "manpower_rows": [
                {
                    "id": manpower_row_id,
                    "role_code": "FOREMAN",
                    "role_label": "Foreman",
                    "claimed_count": 4,
                    "claimed_hours": 8.0,
                    "note": "Updated without losing row file",
                    "sort_order": 0,
                }
            ]
        },
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert preserve_row_update.status_code == 200, preserve_row_update.text
    preserved_manpower = preserve_row_update.json().get("data", {}).get("manpower_rows", [{}])[0]
    assert int(preserved_manpower.get("id") or 0) == manpower_row_id
    preserved_files = preserved_manpower.get("attachment_files") or []
    assert any(str(item.get("file_name") or "") == "manpower-photo.txt" for item in preserved_files)

    update_with_attachment = client.put(
        f"/api/v1/site-logs/{draft_id}",
        json={
            "attachment_rows": [
                {
                    "attachment_type": "PHOTO",
                    "title": "Foundation progress",
                    "reference_no": "PH-211",
                    "note": "Logged at 10:35",
                    "linked_attachment_id": attachment_id,
                    "sort_order": 0,
                }
            ]
        },
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert update_with_attachment.status_code == 200, update_with_attachment.text
    attachment_rows = update_with_attachment.json().get("data", {}).get("attachment_rows") or []
    assert len(attachment_rows) == 1
    assert int(attachment_rows[0].get("linked_attachment_id") or 0) == attachment_id

    empty_draft = _create_draft(
        contractor_headers,  # type: ignore[arg-type]
        project_code=project_code,
        discipline_code=None,
        organization_id=organization_id,
        include_rows=False,
    )
    empty_draft_id = int(empty_draft.get("id") or 0)
    submit_empty = client.post(f"/api/v1/site-logs/{empty_draft_id}/submit", json={"note": "submit"}, headers=contractor_headers)  # type: ignore[arg-type]
    assert submit_empty.status_code == 400, submit_empty.text

    holiday_draft = _create_draft(
        contractor_headers,  # type: ignore[arg-type]
        project_code=project_code,
        discipline_code=None,
        organization_id=organization_id,
        include_rows=False,
        work_status="HOLIDAY",
    )
    holiday_draft_id = int(holiday_draft.get("id") or 0)
    submit_holiday = client.post(
        f"/api/v1/site-logs/{holiday_draft_id}/submit",
        json={"note": "تعطیلی کارگاه"},
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert submit_holiday.status_code == 200, submit_holiday.text
    submit_holiday_data = submit_holiday.json().get("data", {})
    assert str(submit_holiday_data.get("status_code")) == "SUBMITTED"
    assert str(submit_holiday_data.get("work_status")) == "HOLIDAY"
    verify_holiday = client.post(
        f"/api/v1/site-logs/{holiday_draft_id}/verify",
        json={"note": "تایید تعطیلی کارگاه"},
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert verify_holiday.status_code == 200, verify_holiday.text
    assert str(verify_holiday.json().get("data", {}).get("status_code")) == "VERIFIED"

    contractor_verified_write = client.put(
        f"/api/v1/site-logs/{draft_id}",
        json={
            "manpower_rows": [
                {
                    "role_code": "FOREMAN",
                    "role_label": "Foreman",
                    "claimed_count": 4,
                    "claimed_hours": 8.0,
                    "verified_count": 9,
                    "sort_order": 0,
                }
            ]
        },
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert contractor_verified_write.status_code == 403, contractor_verified_write.text

    submit_ok = client.post(f"/api/v1/site-logs/{draft_id}/submit", json={"note": "submit"}, headers=contractor_headers)  # type: ignore[arg-type]
    assert submit_ok.status_code == 200, submit_ok.text
    assert str(submit_ok.json().get("data", {}).get("status_code")) == "SUBMITTED"

    consultant_create = client.post(
        "/api/v1/site-logs/create",
        json={
            "log_type": "DAILY",
            "project_code": project_code,
            "discipline_code": discipline_code,
            "organization_id": int(consultant.get("organization_id") or 0),
            "log_date": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
            "summary": "Consultant should not create",
        },
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert consultant_create.status_code == 403, consultant_create.text

    verify_without_values = client.post(
        f"/api/v1/site-logs/{draft_id}/verify",
        json={"note": "verify without values"},
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert verify_without_values.status_code == 400, verify_without_values.text

    verify_ok = client.post(
        f"/api/v1/site-logs/{draft_id}/verify",
        json={
            "manpower_rows": [{"sort_order": 0, "verified_count": 5, "verified_hours": 8.0}],
            "equipment_rows": [{"sort_order": 0, "verified_count": 2, "verified_status": "ACTIVE", "verified_hours": 5.0}],
            "note": "verified",
        },
        headers=consultant_headers,  # type: ignore[arg-type]
    )
    assert verify_ok.status_code == 200, verify_ok.text
    verified_data = verify_ok.json().get("data", {})
    assert str(verified_data.get("status_code")) == "VERIFIED"
    assert int(((verified_data.get("equipment_rows") or [{}])[0]).get("verified_count") or 0) == 2

    contractor_update_after_verify = client.put(
        f"/api/v1/site-logs/{draft_id}",
        json={"summary": "should fail after verify"},
        headers=contractor_headers,  # type: ignore[arg-type]
    )
    assert contractor_update_after_verify.status_code == 409, contractor_update_after_verify.text
