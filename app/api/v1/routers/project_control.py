from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import User, get_db, has_permission_for_user, require_permission
from app.services.project_control_service import (
    QC_STATUSES,
    csv_text,
    get_source_report,
    list_activity_measurements,
    transition_measurement,
    update_measurement,
)


router = APIRouter(prefix="/project-control", tags=["Project Control"])


class ActivityMeasurementUpdateIn(BaseModel):
    supervisor_today_quantity: Optional[float] = Field(default=None, ge=0)
    supervisor_cumulative_quantity: Optional[float] = Field(default=None, ge=0)
    supervisor_unit: Optional[str] = Field(default=None, max_length=64)
    verified_progress_pct: Optional[float] = Field(default=None, ge=0, le=100)
    qc_status: Optional[str] = Field(default=None, max_length=32)
    qc_note: Optional[str] = None
    note: Optional[str] = None


class ActivityMeasurementTransitionIn(BaseModel):
    target: str = Field(..., max_length=32)


def _filters(
    *,
    project_code: str | None,
    discipline_code: str | None,
    organization_id: int | None,
    organization_contract_id: int | None,
    activity_code: str | None,
    pms_template_code: str | None,
    qc_status: str | None,
    measurement_status: str | None,
    date_from: date | None,
    date_to: date | None,
    search: str | None,
) -> dict[str, object]:
    return {
        "project_code": project_code,
        "discipline_code": discipline_code,
        "organization_id": organization_id,
        "organization_contract_id": organization_contract_id,
        "activity_code": activity_code,
        "pms_template_code": pms_template_code,
        "qc_status": qc_status,
        "measurement_status": measurement_status,
        "date_from": date_from,
        "date_to": date_to,
        "search": search,
    }


def _ensure_qc_permission(db: Session, user: User, payload: ActivityMeasurementUpdateIn) -> None:
    touched_qc = "qc_status" in getattr(payload, "model_fields_set", set()) or "qc_note" in getattr(
        payload, "model_fields_set", set()
    )
    if touched_qc and not has_permission_for_user(db, user, "project_control:qc"):
        raise HTTPException(status_code=403, detail="Access denied. Missing permission: project_control:qc")


@router.get("/activity-measurements")
def list_measurements(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    organization_id: Optional[int] = Query(default=None, ge=1),
    organization_contract_id: Optional[int] = Query(default=None, ge=1),
    activity_code: Optional[str] = Query(default=None),
    pms_template_code: Optional[str] = Query(default=None),
    qc_status: Optional[str] = Query(default=None),
    measurement_status: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("project_control:view")),
):
    return list_activity_measurements(
        db,
        user,
        filters=_filters(
            project_code=project_code,
            discipline_code=discipline_code,
            organization_id=organization_id,
            organization_contract_id=organization_contract_id,
            activity_code=activity_code,
            pms_template_code=pms_template_code,
            qc_status=qc_status,
            measurement_status=measurement_status,
            date_from=date_from,
            date_to=date_to,
            search=search,
        ),
        page=page,
        page_size=page_size,
    )


@router.patch("/activity-measurements/{row_id}")
def patch_measurement(
    row_id: int,
    payload: ActivityMeasurementUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("project_control:measure")),
):
    _ensure_qc_permission(db, user, payload)
    body = payload.model_dump(exclude_unset=True)
    qc = str(body.get("qc_status") or "").strip().upper()
    if qc and qc not in QC_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid qc_status: {qc}")
    return {"ok": True, "data": update_measurement(db, row_id, body, user)}


@router.post("/activity-measurements/{row_id}/transition")
def transition_measurement_row(
    row_id: int,
    payload: ActivityMeasurementTransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("project_control:qc")),
):
    return {"ok": True, "data": transition_measurement(db, row_id, payload.target, user)}


@router.get("/activity-measurements.csv")
def export_measurements_csv(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    organization_id: Optional[int] = Query(default=None, ge=1),
    organization_contract_id: Optional[int] = Query(default=None, ge=1),
    activity_code: Optional[str] = Query(default=None),
    pms_template_code: Optional[str] = Query(default=None),
    qc_status: Optional[str] = Query(default=None),
    measurement_status: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    search: Optional[str] = Query(default=None),
    shape: str = Query(default="wide"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("project_control:view")),
):
    normalized_shape = str(shape or "wide").strip().lower()
    if normalized_shape not in {"wide", "long"}:
        raise HTTPException(status_code=400, detail="shape must be wide or long.")
    text = csv_text(
        db,
        user,
        filters=_filters(
            project_code=project_code,
            discipline_code=discipline_code,
            organization_id=organization_id,
            organization_contract_id=organization_contract_id,
            activity_code=activity_code,
            pms_template_code=pms_template_code,
            qc_status=qc_status,
            measurement_status=measurement_status,
            date_from=date_from,
            date_to=date_to,
            search=search,
        ),
        shape=normalized_shape,
    )
    filename = f"project-control-activity-measurements-{normalized_shape}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        BytesIO(text.encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


@router.get("/activity-measurements/{row_id}/source-report")
def source_report(
    row_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("project_control:view")),
):
    return get_source_report(db, user, row_id)
