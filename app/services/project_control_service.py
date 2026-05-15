from __future__ import annotations

import csv
from datetime import date, datetime
from io import StringIO
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.dependencies import User, apply_organization_query_filters, apply_scope_query_filters
from app.db.models import SiteLog, SiteLogActivityPmsMapping, SiteLogActivityRow


QC_STATUSES = {"PENDING", "PASSED", "FAILED", "NA"}
MEASUREMENT_STATUSES = {"DRAFT", "MEASURED", "VERIFIED"}
EDITABLE_MEASUREMENT_STATUSES = {"DRAFT", "MEASURED"}


WIDE_COLUMNS: list[tuple[str, str]] = [
    ("row_id", "Row ID"),
    ("log_id", "Log ID"),
    ("log_no", "Log No"),
    ("log_date", "Log Date"),
    ("status_code", "Log Status"),
    ("project_code", "Project"),
    ("discipline_code", "Discipline"),
    ("organization_id", "Organization ID"),
    ("organization_name", "Organization"),
    ("organization_contract_id", "Contract ID"),
    ("contract_number", "Contract No"),
    ("contract_subject", "Contract Subject"),
    ("activity_code", "Activity Code"),
    ("activity_title", "Activity Title"),
    ("location", "Location"),
    ("contractor_unit", "Contractor Unit"),
    ("contractor_today_quantity", "Contractor Today Qty"),
    ("contractor_cumulative_quantity", "Contractor Cumulative Qty"),
    ("supervisor_unit", "Supervisor Unit"),
    ("supervisor_today_quantity", "Supervisor Today Qty"),
    ("supervisor_cumulative_quantity", "Supervisor Cumulative Qty"),
    ("claimed_progress_pct", "Claimed Progress %"),
    ("verified_progress_pct", "Verified Progress %"),
    ("pms_template_code", "PMS Template"),
    ("pms_step_code", "Current PMS Step"),
    ("pms_step_title", "Current PMS Step Title"),
    ("pms_step_weight_pct", "Current PMS Weight %"),
    ("qc_status", "QC Status"),
    ("qc_at", "QC At"),
    ("qc_by_user_id", "QC By"),
    ("qc_note", "QC Note"),
    ("measurement_status", "Measurement Status"),
    ("measurement_updated_at", "Measurement Updated At"),
    ("measurement_updated_by_user_id", "Measurement Updated By"),
    ("note", "Note"),
]

LONG_EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("step_code", "Step Code"),
    ("step_title", "Step Title"),
    ("step_weight_pct", "Step Weight %"),
    ("is_current_step", "Is Current Step"),
]


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None


def _day_start(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    return datetime(value.year, value.month, value.day)


def _day_end(value: date | datetime | None) -> datetime | None:
    start = _day_start(value)
    return start.replace(hour=23, minute=59, second=59, microsecond=999999) if start else None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_round(value: Any) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, 2) if parsed is not None else None


def _base_query(db: Session, user: User):
    query = (
        db.query(SiteLogActivityRow)
        .join(SiteLog, SiteLog.id == SiteLogActivityRow.site_log_id)
        .options(
            joinedload(SiteLogActivityRow.site_log).joinedload(SiteLog.organization),
            joinedload(SiteLogActivityRow.site_log).joinedload(SiteLog.organization_contract),
            selectinload(SiteLogActivityRow.pms_mapping).selectinload(SiteLogActivityPmsMapping.steps),
        )
        .filter(SiteLog.status_code.in_(["SUBMITTED", "VERIFIED", "CLOSED"]))
    )
    query = apply_scope_query_filters(query, db, user, project_column=SiteLog.project_code, discipline_column=SiteLog.discipline_code)
    query = apply_organization_query_filters(query, db, user, organization_column=SiteLog.organization_id)
    return query


def _apply_filters(query, filters: dict[str, Any]):
    project_code = _upper(filters.get("project_code"))
    discipline_code = _upper(filters.get("discipline_code"))
    activity_code = _upper(filters.get("activity_code"))
    pms_template_code = _upper(filters.get("pms_template_code"))
    qc_status = _upper(filters.get("qc_status"))
    measurement_status = _upper(filters.get("measurement_status"))
    organization_id = filters.get("organization_id")
    organization_contract_id = filters.get("organization_contract_id") or filters.get("contract_id")
    date_from = filters.get("date_from") or filters.get("log_date_from")
    date_to = filters.get("date_to") or filters.get("log_date_to")
    search = _norm(filters.get("search"))

    if project_code:
        query = query.filter(SiteLog.project_code == project_code)
    if discipline_code:
        query = query.filter(SiteLog.discipline_code == discipline_code)
    if activity_code:
        query = query.filter(SiteLogActivityRow.activity_code == activity_code)
    if pms_template_code:
        query = query.filter(SiteLogActivityRow.pms_template_code == pms_template_code)
    if qc_status:
        if qc_status not in QC_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid qc_status: {qc_status}")
        query = query.filter(SiteLogActivityRow.qc_status == qc_status)
    if measurement_status:
        if measurement_status not in MEASUREMENT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid measurement_status: {measurement_status}")
        query = query.filter(SiteLogActivityRow.measurement_status == measurement_status)
    if organization_id:
        query = query.filter(SiteLog.organization_id == int(organization_id))
    if organization_contract_id:
        query = query.filter(SiteLog.organization_contract_id == int(organization_contract_id))
    if date_from:
        query = query.filter(SiteLog.log_date >= _day_start(date_from))
    if date_to:
        query = query.filter(SiteLog.log_date <= _day_end(date_to))
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                SiteLog.log_no.ilike(pattern),
                SiteLog.project_code.ilike(pattern),
                SiteLog.discipline_code.ilike(pattern),
                SiteLog.contract_number.ilike(pattern),
                SiteLog.contract_subject.ilike(pattern),
                SiteLogActivityRow.activity_code.ilike(pattern),
                SiteLogActivityRow.activity_title.ilike(pattern),
                SiteLogActivityRow.location.ilike(pattern),
                SiteLogActivityRow.unit.ilike(pattern),
                SiteLogActivityRow.supervisor_unit.ilike(pattern),
                SiteLogActivityRow.pms_template_code.ilike(pattern),
                SiteLogActivityRow.pms_step_title.ilike(pattern),
                SiteLogActivityRow.qc_status.ilike(pattern),
                SiteLogActivityRow.measurement_status.ilike(pattern),
            )
        )
    return query


def _pms_steps(row: SiteLogActivityRow) -> list[dict[str, Any]]:
    mapping = row.pms_mapping
    steps = list(getattr(mapping, "steps", []) or [])
    if not steps and row.pms_step_code:
        return [
            {
                "step_code": row.pms_step_code,
                "step_title": row.pms_step_title,
                "step_weight_pct": _safe_round(row.pms_step_weight_pct),
                "is_current_step": True,
                "sort_order": 0,
            }
        ]
    out: list[dict[str, Any]] = []
    current = _upper(row.pms_step_code)
    for step in sorted(steps, key=lambda item: (int(getattr(item, "sort_order", 0) or 0), int(getattr(item, "id", 0) or 0))):
        step_code = _upper(getattr(step, "step_code", None))
        out.append(
            {
                "step_code": step_code,
                "step_title": getattr(step, "step_title", None),
                "step_weight_pct": _safe_round(getattr(step, "weight_pct", None)),
                "is_current_step": bool(current and step_code == current),
                "sort_order": getattr(step, "sort_order", None),
            }
        )
    return out


def serialize_activity_measurement(row: SiteLogActivityRow) -> dict[str, Any]:
    log = row.site_log
    organization = getattr(log, "organization", None)
    contract = getattr(log, "organization_contract", None)
    qc_status = _upper(row.qc_status) or "PENDING"
    measurement_status = _upper(row.measurement_status) or "DRAFT"
    return {
        "row_id": row.id,
        "log_id": log.id if log else row.site_log_id,
        "log_no": getattr(log, "log_no", None),
        "log_date": _to_iso(getattr(log, "log_date", None)),
        "status_code": getattr(log, "status_code", None),
        "project_code": getattr(log, "project_code", None),
        "discipline_code": getattr(log, "discipline_code", None),
        "organization_id": getattr(log, "organization_id", None),
        "organization_name": getattr(organization, "name", None),
        "organization_contract_id": getattr(log, "organization_contract_id", None),
        "contract_number": getattr(log, "contract_number", None) or getattr(contract, "contract_number", None),
        "contract_subject": getattr(log, "contract_subject", None) or getattr(contract, "subject", None),
        "activity_code": row.activity_code,
        "activity_title": row.activity_title,
        "location": row.location,
        "contractor_unit": row.unit,
        "contractor_today_quantity": _safe_round(row.today_quantity),
        "contractor_cumulative_quantity": _safe_round(row.cumulative_quantity),
        "supervisor_unit": row.supervisor_unit or row.unit,
        "supervisor_today_quantity": _safe_round(row.supervisor_today_quantity),
        "supervisor_cumulative_quantity": _safe_round(row.supervisor_cumulative_quantity),
        "claimed_progress_pct": _safe_round(row.claimed_progress_pct),
        "verified_progress_pct": _safe_round(row.verified_progress_pct),
        "pms_template_code": row.pms_template_code,
        "pms_template_title": row.pms_template_title,
        "pms_template_version": row.pms_template_version,
        "pms_step_code": row.pms_step_code,
        "pms_step_title": row.pms_step_title,
        "pms_step_weight_pct": _safe_round(row.pms_step_weight_pct),
        "pms_steps": _pms_steps(row),
        "qc_status": qc_status,
        "qc_at": _to_iso(row.qc_at),
        "qc_by_user_id": row.qc_by_user_id,
        "qc_note": row.qc_note,
        "measurement_status": measurement_status,
        "measurement_updated_at": _to_iso(row.measurement_updated_at),
        "measurement_updated_by_user_id": row.measurement_updated_by_user_id,
        "activity_status": row.activity_status,
        "stop_reason": row.stop_reason,
        "note": row.note,
        "sort_order": row.sort_order,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_qc: dict[str, int] = {}
    by_measurement: dict[str, int] = {}
    claimed_values: list[float] = []
    verified_values: list[float] = []
    for row in rows:
        qc = _upper(row.get("qc_status")) or "PENDING"
        measurement = _upper(row.get("measurement_status")) or "DRAFT"
        by_qc[qc] = by_qc.get(qc, 0) + 1
        by_measurement[measurement] = by_measurement.get(measurement, 0) + 1
        if row.get("claimed_progress_pct") is not None:
            claimed_values.append(float(row["claimed_progress_pct"]))
        if row.get("verified_progress_pct") is not None:
            verified_values.append(float(row["verified_progress_pct"]))
    claimed_avg = round(sum(claimed_values) / len(claimed_values), 2) if claimed_values else None
    verified_avg = round(sum(verified_values) / len(verified_values), 2) if verified_values else None
    return {
        "total": len(rows),
        "by_qc_status": by_qc,
        "by_measurement_status": by_measurement,
        "draft": by_measurement.get("DRAFT", 0),
        "measured": by_measurement.get("MEASURED", 0),
        "verified": by_measurement.get("VERIFIED", 0),
        "qc_pending": by_qc.get("PENDING", 0),
        "qc_passed": by_qc.get("PASSED", 0),
        "qc_failed": by_qc.get("FAILED", 0),
        "contractor_today_quantity": round(sum(float(row.get("contractor_today_quantity") or 0) for row in rows), 2),
        "supervisor_today_quantity": round(sum(float(row.get("supervisor_today_quantity") or 0) for row in rows), 2),
        "claimed_avg_progress_pct": claimed_avg,
        "verified_avg_progress_pct": verified_avg,
        "progress_delta_pct": (
            round((verified_avg or 0.0) - (claimed_avg or 0.0), 2)
            if claimed_avg is not None or verified_avg is not None
            else None
        ),
    }


def list_activity_measurements(
    db: Session,
    user: User,
    *,
    filters: dict[str, Any] | None = None,
    page: int = 1,
    page_size: int = 50,
    include_all_rows: bool = False,
) -> dict[str, Any]:
    query = _apply_filters(_base_query(db, user), filters or {})
    rows = [
        serialize_activity_measurement(row)
        for row in query.order_by(SiteLog.log_date.desc(), SiteLog.id.desc(), SiteLogActivityRow.sort_order.asc(), SiteLogActivityRow.id.asc()).all()
    ]
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(5000, int(page_size or 50)))
    total = len(rows)
    pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    if include_all_rows:
        page_rows = rows
    else:
        offset = (safe_page - 1) * safe_page_size
        page_rows = rows[offset : offset + safe_page_size]
    return {
        "ok": True,
        "summary": _summary(rows),
        "columns": [{"key": key, "label": label} for key, label in WIDE_COLUMNS],
        "data": page_rows,
        "pagination": {
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
            "pages": pages,
            "has_prev": safe_page > 1,
            "has_next": safe_page < pages,
        },
    }


def load_activity_row_for_update(db: Session, user: User, row_id: int) -> SiteLogActivityRow:
    row = (
        _base_query(db, user)
        .filter(SiteLogActivityRow.id == int(row_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Activity measurement row not found")
    return row


def update_measurement(db: Session, row_id: int, payload: dict[str, Any], user: User) -> dict[str, Any]:
    row = load_activity_row_for_update(db, user, row_id)
    if _upper(row.measurement_status) == "VERIFIED":
        raise HTTPException(status_code=409, detail="Verified measurement rows cannot be edited.")

    now = datetime.utcnow()
    value_fields = {
        "supervisor_today_quantity",
        "supervisor_cumulative_quantity",
        "supervisor_unit",
        "verified_progress_pct",
        "note",
    }
    qc_fields = {"qc_status", "qc_note"}
    touched_value = False
    for field in value_fields:
        if field in payload:
            value = payload.get(field)
            if field in {"supervisor_today_quantity", "supervisor_cumulative_quantity", "verified_progress_pct"}:
                value = _safe_float(value)
            if field == "supervisor_unit":
                value = _norm(value) or None
            if field == "note":
                value = _norm(value) or None
            setattr(row, field, value)
            touched_value = True
    for field in qc_fields:
        if field in payload:
            value = payload.get(field)
            if field == "qc_status":
                value = _upper(value) or "PENDING"
                if value not in QC_STATUSES:
                    raise HTTPException(status_code=400, detail=f"Invalid qc_status: {value}")
                row.qc_status = value
                row.qc_at = now
                row.qc_by_user_id = getattr(user, "id", None)
            if field == "qc_note":
                row.qc_note = _norm(value) or None
    if touched_value and _upper(row.measurement_status) == "DRAFT":
        row.measurement_status = "MEASURED"
    row.measurement_updated_at = now
    row.measurement_updated_by_user_id = getattr(user, "id", None)
    db.commit()
    db.refresh(row)
    return serialize_activity_measurement(row)


def transition_measurement(db: Session, row_id: int, target: str, user: User) -> dict[str, Any]:
    row = load_activity_row_for_update(db, user, row_id)
    target_status = _upper(target)
    if target_status != "VERIFIED":
        raise HTTPException(status_code=400, detail="Only VERIFIED transition is supported.")
    if _upper(row.qc_status) != "PASSED":
        raise HTTPException(status_code=400, detail="QC must be PASSED before verification.")
    if row.verified_progress_pct is None:
        raise HTTPException(status_code=400, detail="verified_progress_pct is required before verification.")
    row.measurement_status = "VERIFIED"
    row.measurement_updated_at = datetime.utcnow()
    row.measurement_updated_by_user_id = getattr(user, "id", None)
    db.commit()
    db.refresh(row)
    return serialize_activity_measurement(row)


def get_source_report(db: Session, user: User, row_id: int) -> dict[str, Any]:
    row = load_activity_row_for_update(db, user, row_id)
    log = row.site_log
    return {
        "ok": True,
        "data": {
            "row": serialize_activity_measurement(row),
            "site_log": {
                "id": log.id,
                "log_no": log.log_no,
                "log_type": log.log_type,
                "status_code": log.status_code,
                "project_code": log.project_code,
                "discipline_code": log.discipline_code,
                "organization_id": log.organization_id,
                "organization_name": log.organization.name if log.organization else None,
                "organization_contract_id": log.organization_contract_id,
                "contract_number": log.contract_number,
                "contract_subject": log.contract_subject,
                "log_date": _to_iso(log.log_date),
                "summary": log.summary,
                "current_work_summary": log.current_work_summary,
                "next_plan_summary": log.next_plan_summary,
            },
        },
    }


def csv_text(db: Session, user: User, *, filters: dict[str, Any] | None = None, shape: str = "wide") -> str:
    normalized_shape = _norm(shape).lower() or "wide"
    payload = list_activity_measurements(db, user, filters=filters, page=1, page_size=5000, include_all_rows=True)
    rows = list(payload.get("data") or [])
    if normalized_shape == "long":
        fieldnames = [key for key, _label in WIDE_COLUMNS] + [key for key, _label in LONG_EXTRA_COLUMNS]
        export_rows: list[dict[str, Any]] = []
        for row in rows:
            steps = list(row.get("pms_steps") or [])
            if not steps:
                steps = [{"step_code": None, "step_title": None, "step_weight_pct": None, "is_current_step": False}]
            base = {key: row.get(key) for key, _label in WIDE_COLUMNS}
            for step in steps:
                export_rows.append(
                    {
                        **base,
                        "step_code": step.get("step_code"),
                        "step_title": step.get("step_title"),
                        "step_weight_pct": step.get("step_weight_pct"),
                        "is_current_step": step.get("is_current_step"),
                    }
                )
    else:
        fieldnames = [key for key, _label in WIDE_COLUMNS]
        export_rows = [{key: row.get(key) for key in fieldnames} for row in rows]

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in export_rows:
        writer.writerow(row)
    return buffer.getvalue()
