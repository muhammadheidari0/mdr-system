from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import (
    User,
    allow_editor,
    allow_viewer,
    apply_organization_query_filters,
    apply_scope_query_filters,
    enforce_organization_access,
    enforce_scope_access,
    get_db,
)
from app.db.models import (
    CommItem,
    Discipline,
    ItemAttachment,
    ItemComment,
    ItemFieldAudit,
    ItemRelation,
    ItemSequence,
    ItemStatusLog,
    NcrDetail,
    Organization,
    Project,
    ReviewResult,
    RfiDetail,
    TechDetail,
    TechSubtype,
    User as DbUser,
    WorkflowStatus,
    WorkflowTransition,
)
from app.services.folder_service import safe_name
from app.services.storage import StorageManager
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import enqueue_comm_item_mirror_job, resolve_mirror_enqueue_plan


router = APIRouter(prefix="/comm-items", tags=["Communication Items"])

VALID_ITEM_TYPES = {"RFI", "NCR", "TECH"}
RELATION_TYPES = {"CAUSED_BY", "RESULTS_IN", "REFERENCES", "SUPERSEDES", "LINKED_TO_CLAIM"}
ATTACHMENT_SCOPES = {"GENERAL", "REFERENCE", "RESPONSE"}
ATTACHMENT_SLOT_RULES: dict[str, dict[str, str]] = {
    "RFI": {
        "GENERAL": "GENERAL_ATTACHMENT",
        "REFERENCE": "RFI_REFERENCE",
        "RESPONSE": "RFI_RESPONSE",
    },
    "NCR": {
        "GENERAL": "GENERAL_ATTACHMENT",
        "REFERENCE": "NCR_REFERENCE",
        "RESPONSE": "NCR_RESPONSE",
    },
    "TECH": {
        "GENERAL": "GENERAL_ATTACHMENT",
        "REFERENCE": "TECH_REFERENCE",
        "RESPONSE": "TECH_RESPONSE",
    },
}
FILE_ACCEPT_MATRIX: dict[str, list[str]] = {
    "pdf": [".pdf"],
    "image": [".png", ".jpg", ".jpeg"],
    "sheet": [".xls", ".xlsx"],
    "cad": [".dwg", ".dxf"],
    "model": [".ifc"],
    "archive": [".zip"],
}
REMOVED_TECH_REPORT_SUBTYPES = {
    "DAILY_REPORT",
    "WEEKLY_REPORT",
    "MANPOWER_REPORT",
    "EQUIPMENT_REPORT",
}
TERMINAL_BY_TYPE: dict[str, set[str]] = {
    "RFI": {"CLOSED", "SUPERSEDED"},
    "NCR": {"CLOSED"},
    "TECH": {"CLOSED"},
}
SENSITIVE_FIELDS = {
    "status_code",
    "response_due_date",
    "assignee_user_id",
    "recipient_org_id",
    "claim_notice_required",
    "notice_deadline",
    "contract_clause_ref",
}


def _norm(value: Optional[str]) -> str:
    return str(value or "").strip()


def _upper(value: Optional[str]) -> str:
    return _norm(value).upper()


def _json_dumps(values: list[str] | None) -> str | None:
    if not values:
        return None
    cleaned = [str(v or "").strip() for v in values if str(v or "").strip()]
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)


def _json_loads_list(value: Optional[str]) -> list[str]:
    raw = _norm(value)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(v or "").strip() for v in parsed if str(v or "").strip()]


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _is_open(item_type: str, status_code: str) -> bool:
    return _upper(status_code) not in TERMINAL_BY_TYPE.get(_upper(item_type), {"CLOSED"})


def _calc_aging_days(item: CommItem) -> int | None:
    if not item.response_due_date or not _is_open(item.item_type, item.status_code):
        return None
    delta = datetime.utcnow() - item.response_due_date
    return max(0, int(delta.days))


def _is_overdue(item: CommItem) -> bool:
    if not item.response_due_date:
        return False
    return _is_open(item.item_type, item.status_code) and item.response_due_date < datetime.utcnow()


def _load_item_or_404(db: Session, item_id: int) -> CommItem:
    row = (
        db.query(CommItem)
        .options(
            joinedload(CommItem.rfi_detail),
            joinedload(CommItem.ncr_detail),
            joinedload(CommItem.tech_detail),
            joinedload(CommItem.recipient_org),
            joinedload(CommItem.organization),
            joinedload(CommItem.assignee_user),
            joinedload(CommItem.created_by),
        )
        .filter(CommItem.id == item_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return row


def _enforce_item_scope(db: Session, user: User, item: CommItem) -> None:
    enforce_scope_access(
        db,
        user,
        project_code=item.project_code,
        discipline_code=item.discipline_code,
    )
    enforce_organization_access(db, user, organization_id=item.organization_id)


def _require_project_and_discipline(db: Session, project_code: str, discipline_code: str) -> None:
    project = db.query(Project).filter(Project.code == project_code).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    discipline = db.query(Discipline).filter(Discipline.code == discipline_code).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")


def _check_optional_org(db: Session, org_id: int | None) -> None:
    if not org_id:
        return
    row = db.query(Organization).filter(Organization.id == int(org_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Organization not found: {org_id}")


def _check_optional_user(db: Session, user_id: int | None) -> None:
    if not user_id:
        return
    row = db.query(DbUser).filter(DbUser.id == int(user_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")


def _next_item_no(
    db: Session,
    *,
    project_code: str,
    item_type: str,
    discipline_code: str,
) -> str:
    pcode = _upper(project_code)
    itype = _upper(item_type)
    dcode = _upper(discipline_code)
    seq = (
        db.query(ItemSequence)
        .filter(
            ItemSequence.project_code == pcode,
            ItemSequence.item_type == itype,
            ItemSequence.discipline_code == dcode,
        )
        .with_for_update()
        .first()
    )
    if seq:
        value = int(seq.next_value or 1)
        seq.next_value = value + 1
        seq.updated_at = datetime.utcnow()
        return f"{pcode}-{itype}-{dcode}-{value:04d}"

    seq = ItemSequence(
        project_code=pcode,
        item_type=itype,
        discipline_code=dcode,
        next_value=2,
        updated_at=datetime.utcnow(),
    )
    db.add(seq)
    return f"{pcode}-{itype}-{dcode}-0001"


def _record_status_log(
    db: Session,
    *,
    item_id: int,
    from_status_code: str | None,
    to_status_code: str,
    changed_by_id: int | None,
    note: str | None = None,
) -> None:
    db.add(
        ItemStatusLog(
            item_id=item_id,
            from_status_code=_upper(from_status_code) or None,
            to_status_code=_upper(to_status_code),
            changed_by_id=changed_by_id,
            changed_at=datetime.utcnow(),
            note=_norm(note) or None,
        )
    )


def _record_field_audit(
    db: Session,
    *,
    item_id: int,
    field_name: str,
    old_value: Any,
    new_value: Any,
    changed_by_id: int | None,
) -> None:
    db.add(
        ItemFieldAudit(
            item_id=item_id,
            field_name=field_name,
            old_value=None if old_value is None else str(old_value),
            new_value=None if new_value is None else str(new_value),
            changed_by_id=changed_by_id,
            changed_at=datetime.utcnow(),
        )
    )


def _validate_transition_exists(db: Session, item_type: str, from_status: str, to_status: str) -> WorkflowTransition:
    row = (
        db.query(WorkflowTransition)
        .filter(
            WorkflowTransition.item_type == item_type,
            WorkflowTransition.from_status_code == from_status,
            WorkflowTransition.to_status_code == to_status,
            WorkflowTransition.is_active.is_(True),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=409, detail=f"Invalid transition: {from_status} -> {to_status}")
    return row


def _validate_status_exists(db: Session, item_type: str, status_code: str) -> None:
    row = (
        db.query(WorkflowStatus.id)
        .filter(
            WorkflowStatus.item_type == item_type,
            WorkflowStatus.code == status_code,
            WorkflowStatus.is_active.is_(True),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail=f"Unknown status `{status_code}` for `{item_type}`.")


def _ensure_positive_note_if_required(note: str | None, transition: WorkflowTransition) -> None:
    if transition.requires_note and not _norm(note):
        raise HTTPException(status_code=400, detail="Transition note is required.")


def _validate_business_rules(item: CommItem) -> None:
    item_type = _upper(item.item_type)
    status_code = _upper(item.status_code)

    if item_type == "RFI":
        if item.ncr_detail or item.tech_detail:
            raise HTTPException(status_code=400, detail="RFI item cannot include NCR/TECH details.")
        detail = item.rfi_detail
        if not detail:
            raise HTTPException(status_code=400, detail="RFI details are required.")
        if status_code == "SUBMITTED":
            if not item.project_code or not item.discipline_code or not item.recipient_org_id:
                raise HTTPException(status_code=400, detail="RFI submit requires project/discipline/recipient.")
            if len(_norm(detail.question_text)) < 20:
                raise HTTPException(status_code=400, detail="RFI submit requires question_text (min 20 chars).")
            if not item.response_due_date:
                raise HTTPException(status_code=400, detail="RFI submit requires response_due_date.")
        if status_code == "ANSWERED":
            if not _norm(detail.answer_text):
                raise HTTPException(status_code=400, detail="RFI ANSWERED requires answer_text.")
            if not detail.answered_at:
                raise HTTPException(status_code=400, detail="RFI ANSWERED requires answered_at.")
        if status_code == "SUPERSEDED":
            if not item.is_superseded or not item.superseded_by_item_id:
                raise HTTPException(
                    status_code=400,
                    detail="RFI SUPERSEDED requires is_superseded and superseded_by_item_id.",
                )

    if item_type == "NCR":
        if item.rfi_detail or item.tech_detail:
            raise HTTPException(status_code=400, detail="NCR item cannot include RFI/TECH details.")
        detail = item.ncr_detail
        if not detail:
            raise HTTPException(status_code=400, detail="NCR details are required.")
        if status_code == "ISSUED":
            if len(_norm(detail.nonconformance_text)) < 20:
                raise HTTPException(status_code=400, detail="NCR ISSUED requires nonconformance_text (min 20 chars).")
            if not _norm(detail.kind) or not _norm(detail.severity):
                raise HTTPException(status_code=400, detail="NCR ISSUED requires kind and severity.")
        if status_code == "CONTRACTOR_REPLY":
            if not _norm(detail.rectification_method):
                raise HTTPException(status_code=400, detail="NCR CONTRACTOR_REPLY requires rectification_method.")
        if status_code in {"VERIFIED", "CLOSED"}:
            if not _norm(detail.verification_note):
                raise HTTPException(status_code=400, detail=f"NCR {status_code} requires verification_note.")
            if not detail.verified_at:
                raise HTTPException(status_code=400, detail=f"NCR {status_code} requires verified_at.")

    if item_type == "TECH":
        if item.rfi_detail or item.ncr_detail:
            raise HTTPException(status_code=400, detail="TECH item cannot include RFI/NCR details.")
        detail = item.tech_detail
        if not detail:
            raise HTTPException(status_code=400, detail="TECH details are required.")
        if status_code == "SUBMITTED":
            if not item.recipient_org_id or not item.response_due_date:
                raise HTTPException(status_code=400, detail="TECH SUBMITTED requires recipient_org_id and response_due_date.")
        if _upper(detail.tech_subtype_code) == "SUBMITTAL":
            if not _norm(detail.document_no) or not _norm(detail.revision) or not item.response_due_date:
                raise HTTPException(
                    status_code=400,
                    detail="TECH SUBMITTAL requires document_no, revision, and response_due_date.",
                )
        if detail.review_result_code and status_code not in {
            "IN_REVIEW",
            "APPROVED",
            "APPROVED_AS_NOTED",
            "REVISE_RESUBMIT",
            "REJECTED",
            "CLOSED",
        }:
            raise HTTPException(
                status_code=400,
                detail="TECH review_result is only valid in review/approval statuses.",
            )


def _item_storage_dir(db: Session, item: CommItem, file_kind: str, scope_code: str = "GENERAL") -> Path:
    base = StorageManager(db).get_correspondence_base_path()
    kind_folder = {
        "pdf": "PDF",
        "native": "Native",
        "attachment": "Attachment",
    }.get(file_kind, "Attachment")
    scope_folder = {
        "GENERAL": "General",
        "REFERENCE": "Reference",
        "RESPONSE": "Response",
    }.get(_upper(scope_code), "General")
    item_no = safe_name(item.item_no or f"ITEM-{item.id}")
    path = base / "comm_items" / item_no / scope_folder / kind_folder
    path.mkdir(parents=True, exist_ok=True)
    return path


TAB_RULES: dict[tuple[str, str], dict[str, Any]] = {
    ("contractor", "execution"): {"item_types": ["TECH"]},
    ("contractor", "requests"): {"item_types": ["RFI"]},
    ("contractor", "quality"): {"item_types": ["NCR"]},
    ("consultant", "defects"): {"item_types": ["NCR"]},
    ("consultant", "instructions"): {
        "item_types": ["TECH"],
        "tech_subtypes": ["INSTRUCTION", "MOM"],
    },
    ("consultant", "inspection"): {
        "item_types": ["TECH"],
        "tech_subtypes": ["IR"],
    },
    ("consultant", "control"): {"item_types": ["RFI", "NCR", "TECH"], "claim_or_overdue_default": True},
}

DEFAULT_STATUS_BY_TYPE = {
    "RFI": "DRAFT",
    "NCR": "ISSUED",
    "TECH": "DRAFT",
}

VALID_PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}
REVIEW_STATUSES = {
    "IN_REVIEW",
    "APPROVED",
    "APPROVED_AS_NOTED",
    "REVISE_RESUBMIT",
    "REJECTED",
    "CLOSED",
}


class RfiDetailIn(BaseModel):
    question_text: Optional[str] = Field(default=None)
    proposed_solution: Optional[str] = Field(default=None)
    answer_text: Optional[str] = Field(default=None)
    answered_at: Optional[datetime] = None
    drawing_refs: list[str] = Field(default_factory=list)
    spec_refs: list[str] = Field(default_factory=list)


class NcrDetailIn(BaseModel):
    kind: Optional[str] = Field(default=None, max_length=32)
    severity: Optional[str] = Field(default=None, max_length=32)
    nonconformance_text: Optional[str] = Field(default=None)
    containment_action: Optional[str] = None
    rectification_method: Optional[str] = None
    rectification_due_date: Optional[datetime] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    preventive_action: Optional[str] = None
    verification_note: Optional[str] = None
    verified_by_id: Optional[int] = Field(default=None, ge=1)
    verified_at: Optional[datetime] = None


class TechDetailIn(BaseModel):
    tech_subtype_code: Optional[str] = Field(default=None, max_length=32)
    document_title: Optional[str] = Field(default=None, max_length=255)
    document_no: Optional[str] = Field(default=None, max_length=128)
    revision: Optional[str] = Field(default=None, max_length=32)
    transmittal_no: Optional[str] = Field(default=None, max_length=128)
    submission_no: Optional[str] = Field(default=None, max_length=128)
    review_cycle_no: Optional[int] = Field(default=None, ge=1)
    review_result_code: Optional[str] = Field(default=None, max_length=32)
    review_note: Optional[str] = None
    reviewed_by_id: Optional[int] = Field(default=None, ge=1)
    reviewed_at: Optional[datetime] = None
    meeting_date: Optional[datetime] = None


class CommItemCreateIn(BaseModel):
    item_type: str = Field(..., min_length=1, max_length=16)
    project_code: str = Field(..., min_length=1, max_length=50)
    discipline_code: str = Field(..., min_length=1, max_length=20)
    organization_id: Optional[int] = Field(default=None, ge=1)
    zone: Optional[str] = Field(default=None, max_length=128)
    title: str = Field(..., min_length=5, max_length=255)
    short_description: Optional[str] = None
    status_code: Optional[str] = Field(default=None, max_length=64)
    priority: Optional[str] = Field(default="NORMAL", max_length=32)
    response_due_date: Optional[datetime] = None
    assignee_user_id: Optional[int] = Field(default=None, ge=1)
    recipient_org_id: Optional[int] = Field(default=None, ge=1)
    contractor_org_id: Optional[int] = Field(default=None, ge=1)
    consultant_org_id: Optional[int] = Field(default=None, ge=1)
    contract_clause_ref: Optional[str] = Field(default=None, max_length=255)
    spec_clause_ref: Optional[str] = Field(default=None, max_length=255)
    wbs_code: Optional[str] = Field(default=None, max_length=64)
    activity_code: Optional[str] = Field(default=None, max_length=64)
    potential_impact_time: bool = False
    potential_impact_cost: bool = False
    potential_impact_quality: bool = False
    potential_impact_safety: bool = False
    impact_note: Optional[str] = None
    delay_days_estimate: Optional[int] = None
    cost_estimate: Optional[float] = None
    claim_notice_required: bool = False
    notice_deadline: Optional[datetime] = None
    is_superseded: bool = False
    superseded_by_item_id: Optional[int] = Field(default=None, ge=1)
    rfi: Optional[RfiDetailIn] = None
    ncr: Optional[NcrDetailIn] = None
    tech: Optional[TechDetailIn] = None


class CommItemUpdateIn(BaseModel):
    project_code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    discipline_code: Optional[str] = Field(default=None, min_length=1, max_length=20)
    organization_id: Optional[int] = Field(default=None, ge=1)
    zone: Optional[str] = Field(default=None, max_length=128)
    title: Optional[str] = Field(default=None, min_length=5, max_length=255)
    short_description: Optional[str] = None
    priority: Optional[str] = Field(default=None, max_length=32)
    response_due_date: Optional[datetime] = None
    assignee_user_id: Optional[int] = Field(default=None, ge=1)
    recipient_org_id: Optional[int] = Field(default=None, ge=1)
    contractor_org_id: Optional[int] = Field(default=None, ge=1)
    consultant_org_id: Optional[int] = Field(default=None, ge=1)
    contract_clause_ref: Optional[str] = Field(default=None, max_length=255)
    spec_clause_ref: Optional[str] = Field(default=None, max_length=255)
    wbs_code: Optional[str] = Field(default=None, max_length=64)
    activity_code: Optional[str] = Field(default=None, max_length=64)
    potential_impact_time: Optional[bool] = None
    potential_impact_cost: Optional[bool] = None
    potential_impact_quality: Optional[bool] = None
    potential_impact_safety: Optional[bool] = None
    impact_note: Optional[str] = None
    delay_days_estimate: Optional[int] = None
    cost_estimate: Optional[float] = None
    claim_notice_required: Optional[bool] = None
    notice_deadline: Optional[datetime] = None
    is_superseded: Optional[bool] = None
    superseded_by_item_id: Optional[int] = Field(default=None, ge=1)
    rfi: Optional[RfiDetailIn] = None
    ncr: Optional[NcrDetailIn] = None
    tech: Optional[TechDetailIn] = None


class CommItemTransitionIn(BaseModel):
    to_status_code: str = Field(..., min_length=1, max_length=64)
    note: Optional[str] = None
    superseded_by_item_id: Optional[int] = Field(default=None, ge=1)


class CommItemCommentIn(BaseModel):
    comment_text: str = Field(..., min_length=1)
    comment_type: str = Field(default="comment", max_length=32)


class CommItemRelationIn(BaseModel):
    to_item_id: int = Field(..., ge=1)
    relation_type: str = Field(..., min_length=1, max_length=64)
    note: Optional[str] = None


def _normalize_item_type(value: str) -> str:
    item_type = _upper(value)
    if item_type not in VALID_ITEM_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported item_type: {value}")
    return item_type


def _normalize_priority(value: Optional[str]) -> str:
    priority = _upper(value or "NORMAL")
    aliases = {"MEDIUM": "NORMAL", "CRITICAL": "URGENT"}
    priority = aliases.get(priority, priority)
    if priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {value}")
    return priority


def _resolve_tab_rule(module_key: Optional[str], tab_key: Optional[str]) -> dict[str, Any] | None:
    module = _norm(module_key).lower()
    tab = _norm(tab_key).lower()
    if not module or not tab:
        return None
    return TAB_RULES.get((module, tab))


def _serialize_rfi_detail(detail: RfiDetail | None) -> dict[str, Any] | None:
    if not detail:
        return None
    return {
        "question_text": detail.question_text,
        "proposed_solution": detail.proposed_solution,
        "answer_text": detail.answer_text,
        "answered_at": _to_iso(detail.answered_at),
        "drawing_refs": _json_loads_list(detail.drawing_refs_json),
        "spec_refs": _json_loads_list(detail.spec_refs_json),
    }


def _serialize_ncr_detail(detail: NcrDetail | None) -> dict[str, Any] | None:
    if not detail:
        return None
    return {
        "kind": detail.kind,
        "severity": detail.severity,
        "nonconformance_text": detail.nonconformance_text,
        "containment_action": detail.containment_action,
        "rectification_method": detail.rectification_method,
        "rectification_due_date": _to_iso(detail.rectification_due_date),
        "root_cause": detail.root_cause,
        "corrective_action": detail.corrective_action,
        "preventive_action": detail.preventive_action,
        "verification_note": detail.verification_note,
        "verified_by_id": detail.verified_by_id,
        "verified_by_name": getattr(getattr(detail, "verified_by", None), "full_name", None),
        "verified_at": _to_iso(detail.verified_at),
    }


def _serialize_tech_detail(detail: TechDetail | None) -> dict[str, Any] | None:
    if not detail:
        return None
    return {
        "tech_subtype_code": detail.tech_subtype_code,
        "document_title": detail.document_title,
        "document_no": detail.document_no,
        "revision": detail.revision,
        "transmittal_no": detail.transmittal_no,
        "submission_no": detail.submission_no,
        "review_cycle_no": detail.review_cycle_no,
        "review_result_code": detail.review_result_code,
        "review_note": detail.review_note,
        "reviewed_by_id": detail.reviewed_by_id,
        "reviewed_by_name": getattr(getattr(detail, "reviewed_by", None), "full_name", None),
        "reviewed_at": _to_iso(detail.reviewed_at),
        "meeting_date": _to_iso(detail.meeting_date),
    }


def _serialize_item(row: CommItem, *, include_details: bool = True) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "item_no": row.item_no,
        "item_type": row.item_type,
        "project_code": row.project_code,
        "discipline_code": row.discipline_code,
        "organization_id": row.organization_id,
        "zone": row.zone,
        "title": row.title,
        "short_description": row.short_description,
        "status_code": row.status_code,
        "priority": row.priority,
        "response_due_date": _to_iso(row.response_due_date),
        "assignee_user_id": row.assignee_user_id,
        "assignee_user_name": getattr(getattr(row, "assignee_user", None), "full_name", None),
        "recipient_org_id": row.recipient_org_id,
        "recipient_org_name": getattr(getattr(row, "recipient_org", None), "name", None),
        "contractor_org_id": row.contractor_org_id,
        "consultant_org_id": row.consultant_org_id,
        "contract_clause_ref": row.contract_clause_ref,
        "spec_clause_ref": row.spec_clause_ref,
        "wbs_code": row.wbs_code,
        "activity_code": row.activity_code,
        "potential_impact_time": bool(row.potential_impact_time),
        "potential_impact_cost": bool(row.potential_impact_cost),
        "potential_impact_quality": bool(row.potential_impact_quality),
        "potential_impact_safety": bool(row.potential_impact_safety),
        "impact_note": row.impact_note,
        "delay_days_estimate": row.delay_days_estimate,
        "cost_estimate": row.cost_estimate,
        "claim_notice_required": bool(row.claim_notice_required),
        "notice_deadline": _to_iso(row.notice_deadline),
        "is_superseded": bool(row.is_superseded),
        "superseded_by_item_id": row.superseded_by_item_id,
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
        "aging_days": _calc_aging_days(row),
        "is_overdue": _is_overdue(row),
    }
    if include_details:
        payload["rfi"] = _serialize_rfi_detail(row.rfi_detail)
        payload["ncr"] = _serialize_ncr_detail(row.ncr_detail)
        payload["tech"] = _serialize_tech_detail(row.tech_detail)
    return payload


def _normalize_attachment_file_kind(value: Optional[str]) -> str:
    normalized = _norm(value).lower()
    if normalized in {"letter", "original"}:
        return "attachment"
    if normalized in {"pdf", "native", "attachment"}:
        return normalized
    return "attachment"


def _normalize_attachment_scope_code(value: Optional[str]) -> str:
    scope_code = _upper(value or "GENERAL")
    if scope_code not in ATTACHMENT_SCOPES:
        raise HTTPException(status_code=400, detail=f"Invalid scope_code: {value}")
    return scope_code


def _resolve_attachment_slot_code(item_type: str, scope_code: str, slot_code: Optional[str]) -> str:
    normalized_item_type = _upper(item_type)
    normalized_scope_code = _normalize_attachment_scope_code(scope_code)
    raw_slot = _upper(slot_code)
    rules = ATTACHMENT_SLOT_RULES.get(normalized_item_type) or {}
    expected_slot = _upper(rules.get(normalized_scope_code))
    if not expected_slot:
        raise HTTPException(
            status_code=400,
            detail=f"Attachment slot rules are not configured for {normalized_item_type}/{normalized_scope_code}.",
        )

    if normalized_scope_code != "GENERAL" and not raw_slot:
        raise HTTPException(status_code=400, detail="slot_code is required when scope_code is REFERENCE/RESPONSE.")

    if not raw_slot:
        return expected_slot

    if raw_slot != expected_slot:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid slot_code `{raw_slot}` for {normalized_item_type}/{normalized_scope_code}. Expected `{expected_slot}`.",
        )
    return expected_slot


def _enforce_detail_payload_match(
    *,
    item_type: str,
    rfi: RfiDetailIn | None,
    ncr: NcrDetailIn | None,
    tech: TechDetailIn | None,
) -> None:
    normalized_item_type = _upper(item_type)
    if normalized_item_type == "RFI":
        if ncr is not None or tech is not None:
            raise HTTPException(status_code=400, detail="RFI payload cannot include NCR/TECH details.")
        return
    if normalized_item_type == "NCR":
        if rfi is not None or tech is not None:
            raise HTTPException(status_code=400, detail="NCR payload cannot include RFI/TECH details.")
        return
    if normalized_item_type == "TECH":
        if rfi is not None or ncr is not None:
            raise HTTPException(status_code=400, detail="TECH payload cannot include RFI/NCR details.")


def _attachment_type_exists_condition(db: Session, attachment_type: Optional[str]):
    normalized = _norm(attachment_type).lower()
    if not normalized:
        return None

    if normalized == "pdf":
        return db.query(ItemAttachment.id).filter(
            ItemAttachment.item_id == CommItem.id,
            or_(
                func.lower(func.coalesce(ItemAttachment.detected_mime, "")) == "application/pdf",
                ItemAttachment.file_name.ilike("%.pdf"),
            ),
        ).exists()
    if normalized == "image":
        return db.query(ItemAttachment.id).filter(
            ItemAttachment.item_id == CommItem.id,
            or_(
                func.lower(func.coalesce(ItemAttachment.detected_mime, "")).like("image/%"),
                ItemAttachment.file_name.ilike("%.png"),
                ItemAttachment.file_name.ilike("%.jpg"),
                ItemAttachment.file_name.ilike("%.jpeg"),
            ),
        ).exists()
    if normalized == "sheet":
        return db.query(ItemAttachment.id).filter(
            ItemAttachment.item_id == CommItem.id,
            or_(
                func.lower(func.coalesce(ItemAttachment.detected_mime, "")).in_(
                    [
                        "application/vnd.ms-excel",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ]
                ),
                ItemAttachment.file_name.ilike("%.xls"),
                ItemAttachment.file_name.ilike("%.xlsx"),
            ),
        ).exists()
    if normalized == "cad":
        return db.query(ItemAttachment.id).filter(
            ItemAttachment.item_id == CommItem.id,
            or_(
                func.lower(func.coalesce(ItemAttachment.detected_mime, "")).in_(
                    [
                        "application/x-dwg",
                        "application/acad",
                        "image/vnd.dwg",
                        "application/dxf",
                        "image/vnd.dxf",
                    ]
                ),
                ItemAttachment.file_name.ilike("%.dwg"),
                ItemAttachment.file_name.ilike("%.dxf"),
            ),
        ).exists()
    if normalized == "model":
        return db.query(ItemAttachment.id).filter(
            ItemAttachment.item_id == CommItem.id,
            or_(
                func.lower(func.coalesce(ItemAttachment.detected_mime, "")).in_(
                    ["model/ifc", "application/x-step"]
                ),
                ItemAttachment.file_name.ilike("%.ifc"),
            ),
        ).exists()
    if normalized == "archive":
        return db.query(ItemAttachment.id).filter(
            ItemAttachment.item_id == CommItem.id,
            or_(
                func.lower(func.coalesce(ItemAttachment.detected_mime, "")) == "application/zip",
                ItemAttachment.file_name.ilike("%.zip"),
            ),
        ).exists()
    raise HTTPException(status_code=400, detail=f"Unsupported attachment_type filter: {attachment_type}")


def _set_item_field(
    db: Session,
    *,
    item: CommItem,
    field_name: str,
    new_value: Any,
    changed_by_id: int | None,
) -> None:
    old_value = getattr(item, field_name, None)
    if old_value == new_value:
        return
    setattr(item, field_name, new_value)
    if field_name in SENSITIVE_FIELDS:
        _record_field_audit(
            db,
            item_id=item.id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            changed_by_id=changed_by_id,
        )


def _require_tech_subtype(db: Session, code: str) -> None:
    normalized = _upper(code)
    if normalized in REMOVED_TECH_REPORT_SUBTYPES:
        raise HTTPException(status_code=400, detail="TECH report subtypes moved to Site Logs.")
    row = db.query(TechSubtype.code).filter(TechSubtype.code == normalized, TechSubtype.is_active.is_(True)).first()
    if not row:
        raise HTTPException(status_code=400, detail=f"Unknown TECH subtype: {code}")


def _require_review_result_if_provided(db: Session, code: str | None) -> None:
    normalized = _upper(code)
    if not normalized:
        return
    row = db.query(ReviewResult.code).filter(ReviewResult.code == normalized, ReviewResult.is_active.is_(True)).first()
    if not row:
        raise HTTPException(status_code=400, detail=f"Unknown review result: {code}")


def _create_rfi_detail(payload: RfiDetailIn | None) -> RfiDetail:
    if payload is None:
        raise HTTPException(status_code=400, detail="RFI detail payload is required.")
    question_text = _norm(payload.question_text)
    if not question_text:
        raise HTTPException(status_code=400, detail="RFI requires question_text.")
    return RfiDetail(
        question_text=question_text,
        proposed_solution=_norm(payload.proposed_solution) or None,
        answer_text=_norm(payload.answer_text) or None,
        answered_at=payload.answered_at,
        drawing_refs_json=_json_dumps(payload.drawing_refs),
        spec_refs_json=_json_dumps(payload.spec_refs),
    )


def _create_ncr_detail(payload: NcrDetailIn | None) -> NcrDetail:
    if payload is None:
        raise HTTPException(status_code=400, detail="NCR detail payload is required.")
    nonconformance_text = _norm(payload.nonconformance_text)
    if not nonconformance_text:
        raise HTTPException(status_code=400, detail="NCR requires nonconformance_text.")
    return NcrDetail(
        kind=_upper(payload.kind) or None,
        severity=_upper(payload.severity) or None,
        nonconformance_text=nonconformance_text,
        containment_action=_norm(payload.containment_action) or None,
        rectification_method=_norm(payload.rectification_method) or None,
        rectification_due_date=payload.rectification_due_date,
        root_cause=_norm(payload.root_cause) or None,
        corrective_action=_norm(payload.corrective_action) or None,
        preventive_action=_norm(payload.preventive_action) or None,
        verification_note=_norm(payload.verification_note) or None,
        verified_by_id=payload.verified_by_id,
        verified_at=payload.verified_at,
    )


def _create_tech_detail(db: Session, payload: TechDetailIn | None) -> TechDetail:
    if payload is None:
        raise HTTPException(status_code=400, detail="TECH detail payload is required.")
    subtype_code = _upper(payload.tech_subtype_code)
    if not subtype_code:
        raise HTTPException(status_code=400, detail="TECH requires tech_subtype_code.")
    _require_tech_subtype(db, subtype_code)
    _require_review_result_if_provided(db, payload.review_result_code)
    return TechDetail(
        tech_subtype_code=subtype_code,
        document_title=_norm(payload.document_title) or None,
        document_no=_norm(payload.document_no) or None,
        revision=_norm(payload.revision) or None,
        transmittal_no=_norm(payload.transmittal_no) or None,
        submission_no=_norm(payload.submission_no) or None,
        review_cycle_no=payload.review_cycle_no,
        review_result_code=_upper(payload.review_result_code) or None,
        review_note=_norm(payload.review_note) or None,
        reviewed_by_id=payload.reviewed_by_id,
        reviewed_at=payload.reviewed_at,
        meeting_date=payload.meeting_date,
    )


def _update_rfi_detail(detail: RfiDetail, payload: RfiDetailIn) -> None:
    if payload.question_text is not None:
        detail.question_text = _norm(payload.question_text)
    if payload.proposed_solution is not None:
        detail.proposed_solution = _norm(payload.proposed_solution) or None
    if payload.answer_text is not None:
        detail.answer_text = _norm(payload.answer_text) or None
    if payload.answered_at is not None:
        detail.answered_at = payload.answered_at
    if payload.drawing_refs:
        detail.drawing_refs_json = _json_dumps(payload.drawing_refs)
    if payload.spec_refs:
        detail.spec_refs_json = _json_dumps(payload.spec_refs)


def _update_ncr_detail(detail: NcrDetail, payload: NcrDetailIn) -> None:
    if payload.kind is not None:
        detail.kind = _upper(payload.kind) or None
    if payload.severity is not None:
        detail.severity = _upper(payload.severity) or None
    if payload.nonconformance_text is not None:
        detail.nonconformance_text = _norm(payload.nonconformance_text)
    if payload.containment_action is not None:
        detail.containment_action = _norm(payload.containment_action) or None
    if payload.rectification_method is not None:
        detail.rectification_method = _norm(payload.rectification_method) or None
    if payload.rectification_due_date is not None:
        detail.rectification_due_date = payload.rectification_due_date
    if payload.root_cause is not None:
        detail.root_cause = _norm(payload.root_cause) or None
    if payload.corrective_action is not None:
        detail.corrective_action = _norm(payload.corrective_action) or None
    if payload.preventive_action is not None:
        detail.preventive_action = _norm(payload.preventive_action) or None
    if payload.verification_note is not None:
        detail.verification_note = _norm(payload.verification_note) or None
    if payload.verified_by_id is not None:
        detail.verified_by_id = payload.verified_by_id
    if payload.verified_at is not None:
        detail.verified_at = payload.verified_at


def _update_tech_detail(db: Session, detail: TechDetail, payload: TechDetailIn) -> None:
    if payload.tech_subtype_code is not None:
        subtype_code = _upper(payload.tech_subtype_code)
        if not subtype_code:
            raise HTTPException(status_code=400, detail="tech_subtype_code cannot be empty.")
        _require_tech_subtype(db, subtype_code)
        detail.tech_subtype_code = subtype_code
    if payload.document_title is not None:
        detail.document_title = _norm(payload.document_title) or None
    if payload.document_no is not None:
        detail.document_no = _norm(payload.document_no) or None
    if payload.revision is not None:
        detail.revision = _norm(payload.revision) or None
    if payload.transmittal_no is not None:
        detail.transmittal_no = _norm(payload.transmittal_no) or None
    if payload.submission_no is not None:
        detail.submission_no = _norm(payload.submission_no) or None
    if payload.review_cycle_no is not None:
        detail.review_cycle_no = payload.review_cycle_no
    if payload.review_result_code is not None:
        _require_review_result_if_provided(db, payload.review_result_code)
        detail.review_result_code = _upper(payload.review_result_code) or None
    if payload.review_note is not None:
        detail.review_note = _norm(payload.review_note) or None
    if payload.reviewed_by_id is not None:
        detail.reviewed_by_id = payload.reviewed_by_id
    if payload.reviewed_at is not None:
        detail.reviewed_at = payload.reviewed_at
    if payload.meeting_date is not None:
        detail.meeting_date = payload.meeting_date


def _serialize_status_log(row: ItemStatusLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "item_id": row.item_id,
        "from_status_code": row.from_status_code,
        "to_status_code": row.to_status_code,
        "changed_by_id": row.changed_by_id,
        "changed_by_name": getattr(getattr(row, "changed_by", None), "full_name", None),
        "changed_at": _to_iso(row.changed_at),
        "note": row.note,
    }


def _serialize_comment(row: ItemComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "item_id": row.item_id,
        "comment_text": row.comment_text,
        "comment_type": row.comment_type,
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "created_at": _to_iso(row.created_at),
    }


def _serialize_attachment(row: ItemAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "item_id": row.item_id,
        "file_name": row.file_name,
        "stored_path": row.stored_path,
        "file_kind": row.file_kind,
        "scope_code": _upper(row.scope_code) or "GENERAL",
        "slot_code": _upper(row.slot_code) or None,
        "note": row.note,
        "mime_type": row.mime_type,
        "detected_mime": row.detected_mime,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "validation_status": row.validation_status,
        "gdrive_file_id": row.gdrive_file_id,
        "mirror_provider": getattr(row, "mirror_provider", None),
        "mirror_remote_id": getattr(row, "mirror_remote_id", None),
        "mirror_remote_url": getattr(row, "mirror_remote_url", None),
        "mirror_status": row.mirror_status,
        "mirror_updated_at": _to_iso(row.mirror_updated_at),
        "uploaded_by_id": row.uploaded_by_id,
        "uploaded_by_name": getattr(getattr(row, "uploaded_by", None), "full_name", None),
        "uploaded_at": _to_iso(row.uploaded_at),
    }


def _serialize_relation(row: ItemRelation) -> dict[str, Any]:
    return {
        "id": row.id,
        "from_item_id": row.from_item_id,
        "to_item_id": row.to_item_id,
        "relation_type": row.relation_type,
        "note": row.note,
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "created_at": _to_iso(row.created_at),
        "from_item_no": getattr(getattr(row, "from_item", None), "item_no", None),
        "to_item_no": getattr(getattr(row, "to_item", None), "item_no", None),
    }


def _load_attachment_or_404(db: Session, attachment_id: int) -> ItemAttachment:
    row = db.query(ItemAttachment).filter(ItemAttachment.id == attachment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return row


def _load_relation_or_404(db: Session, relation_id: int) -> ItemRelation:
    row = db.query(ItemRelation).filter(ItemRelation.id == relation_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Relation not found")
    return row


def _open_status_condition():
    return or_(
        and_(
            CommItem.item_type == "RFI",
            CommItem.status_code.notin_(["CLOSED", "SUPERSEDED"]),
        ),
        and_(CommItem.item_type == "NCR", CommItem.status_code != "CLOSED"),
        and_(CommItem.item_type == "TECH", CommItem.status_code != "CLOSED"),
    )


def _impact_condition():
    return or_(
        CommItem.potential_impact_time.is_(True),
        CommItem.potential_impact_cost.is_(True),
        CommItem.potential_impact_quality.is_(True),
        CommItem.potential_impact_safety.is_(True),
    )


def _overdue_condition(now: datetime):
    return and_(
        CommItem.response_due_date.is_not(None),
        CommItem.response_due_date < now,
        _open_status_condition(),
    )


def _base_items_query(db: Session, user: User):
    query = db.query(CommItem).options(
        joinedload(CommItem.rfi_detail),
        joinedload(CommItem.ncr_detail),
        joinedload(CommItem.tech_detail),
        joinedload(CommItem.created_by),
        joinedload(CommItem.assignee_user),
        joinedload(CommItem.recipient_org),
    )
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=CommItem.project_code,
        discipline_column=CommItem.discipline_code,
    )
    query = apply_organization_query_filters(
        query,
        db,
        user,
        organization_column=CommItem.organization_id,
    )
    return query


@router.get("/catalog")
def get_comm_items_catalog(
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    del user
    statuses = (
        db.query(WorkflowStatus)
        .filter(WorkflowStatus.is_active.is_(True))
        .order_by(WorkflowStatus.item_type.asc(), WorkflowStatus.sort_order.asc(), WorkflowStatus.id.asc())
        .all()
    )
    transitions = (
        db.query(WorkflowTransition)
        .filter(WorkflowTransition.is_active.is_(True))
        .order_by(
            WorkflowTransition.item_type.asc(),
            WorkflowTransition.from_status_code.asc(),
            WorkflowTransition.to_status_code.asc(),
        )
        .all()
    )
    tech_subtypes = (
        db.query(TechSubtype)
        .filter(TechSubtype.is_active.is_(True))
        .filter(~TechSubtype.code.in_(list(REMOVED_TECH_REPORT_SUBTYPES)))
        .order_by(TechSubtype.sort_order.asc(), TechSubtype.code.asc())
        .all()
    )
    review_results = (
        db.query(ReviewResult)
        .filter(ReviewResult.is_active.is_(True))
        .order_by(ReviewResult.sort_order.asc(), ReviewResult.code.asc())
        .all()
    )
    statuses_by_type: dict[str, list[dict[str, Any]]] = {}
    for row in statuses:
        statuses_by_type.setdefault(row.item_type, []).append(
            {
                "id": row.id,
                "item_type": row.item_type,
                "code": row.code,
                "label": row.label,
                "is_terminal": bool(row.is_terminal),
                "sort_order": row.sort_order,
            }
        )
    return {
        "ok": True,
        "item_types": sorted(list(VALID_ITEM_TYPES)),
        "priorities": sorted(list(VALID_PRIORITIES)),
        "relation_types": sorted(list(RELATION_TYPES)),
        "attachment_scopes": sorted(list(ATTACHMENT_SCOPES)),
        "attachment_slot_rules": ATTACHMENT_SLOT_RULES,
        "file_accept_matrix": FILE_ACCEPT_MATRIX,
        "default_status_by_type": DEFAULT_STATUS_BY_TYPE,
        "workflow_statuses": statuses_by_type,
        "workflow_transitions": [
            {
                "id": row.id,
                "item_type": row.item_type,
                "from_status_code": row.from_status_code,
                "to_status_code": row.to_status_code,
                "requires_note": bool(row.requires_note),
            }
            for row in transitions
        ],
        "tech_subtypes": [
            {
                "code": row.code,
                "label": row.label,
                "sort_order": row.sort_order,
            }
            for row in tech_subtypes
        ],
        "review_results": [
            {
                "code": row.code,
                "label": row.label,
                "sort_order": row.sort_order,
            }
            for row in review_results
        ],
        "terminology": {
            "impact_section_label": "Potential Impacts",
            "impact_report_label": "Impact Signals",
            "deprecated_claim_label": "Claim (Deprecated)",
        },
        "tab_rules": [
            {
                "module_key": module_key,
                "tab_key": tab_key,
                "rule": rule,
            }
            for (module_key, tab_key), rule in TAB_RULES.items()
        ],
    }


@router.get("/list")
def list_comm_items(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: Optional[str] = Query(default=None),
    module_key: Optional[str] = Query(default=None),
    tab_key: Optional[str] = Query(default=None),
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    item_type: Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    recipient_org_id: Optional[int] = Query(default=None, ge=1),
    assignee_user_id: Optional[int] = Query(default=None, ge=1),
    tech_subtype_code: Optional[str] = Query(default=None),
    overdue_only: bool = Query(default=False),
    claim_only: bool = Query(default=False),
    impact_only: Optional[bool] = Query(default=None),
    has_reference_attachments: Optional[bool] = Query(default=None),
    has_response_attachments: Optional[bool] = Query(default=None),
    attachment_type: Optional[str] = Query(default=None),
    include_non_claim_control: bool = Query(default=False),
    include_non_impact_control: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    query = _base_items_query(db, user)
    now = datetime.utcnow()
    effective_claim_only = claim_only if impact_only is None else bool(impact_only)
    effective_include_non_claim_control = (
        include_non_claim_control if include_non_impact_control is None else bool(include_non_impact_control)
    )

    rule = _resolve_tab_rule(module_key, tab_key)
    if rule:
        rule_item_types = [str(v or "").upper() for v in rule.get("item_types", []) if str(v or "").strip()]
        if rule_item_types:
            query = query.filter(CommItem.item_type.in_(rule_item_types))
        rule_subtypes = [str(v or "").upper() for v in rule.get("tech_subtypes", []) if str(v or "").strip()]
        if rule_subtypes:
            query = query.filter(CommItem.tech_detail.has(TechDetail.tech_subtype_code.in_(rule_subtypes)))
        if (
            bool(rule.get("claim_or_overdue_default"))
            and not effective_include_non_claim_control
            and not overdue_only
            and not effective_claim_only
        ):
            query = query.filter(or_(_impact_condition(), _overdue_condition(now)))

    if project_code:
        query = query.filter(CommItem.project_code == _upper(project_code))
    if discipline_code:
        query = query.filter(CommItem.discipline_code == _upper(discipline_code))
    if item_type:
        query = query.filter(CommItem.item_type == _normalize_item_type(item_type))
    if status_code:
        query = query.filter(CommItem.status_code == _upper(status_code))
    if priority:
        query = query.filter(CommItem.priority == _normalize_priority(priority))
    if recipient_org_id:
        query = query.filter(CommItem.recipient_org_id == int(recipient_org_id))
    if assignee_user_id:
        query = query.filter(CommItem.assignee_user_id == int(assignee_user_id))
    if tech_subtype_code:
        query = query.filter(CommItem.tech_detail.has(TechDetail.tech_subtype_code == _upper(tech_subtype_code)))
    if search:
        like_term = f"%{_norm(search)}%"
        query = query.filter(
            or_(
                CommItem.item_no.ilike(like_term),
                CommItem.title.ilike(like_term),
                CommItem.short_description.ilike(like_term),
            )
        )
    if overdue_only:
        query = query.filter(_overdue_condition(now))
    if effective_claim_only:
        query = query.filter(or_(_impact_condition(), _overdue_condition(now)))
    if has_reference_attachments is not None:
        reference_exists = (
            db.query(ItemAttachment.id)
            .filter(
                ItemAttachment.item_id == CommItem.id,
                ItemAttachment.scope_code == "REFERENCE",
            )
            .exists()
        )
        query = query.filter(reference_exists if has_reference_attachments else ~reference_exists)
    if has_response_attachments is not None:
        response_exists = (
            db.query(ItemAttachment.id)
            .filter(
                ItemAttachment.item_id == CommItem.id,
                ItemAttachment.scope_code == "RESPONSE",
            )
            .exists()
        )
        query = query.filter(response_exists if has_response_attachments else ~response_exists)
    attachment_type_condition = _attachment_type_exists_condition(db, attachment_type)
    if attachment_type_condition is not None:
        query = query.filter(attachment_type_condition)

    total = query.count()
    rows = (
        query.order_by(CommItem.created_at.desc(), CommItem.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {
        "ok": True,
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [_serialize_item(row, include_details=True) for row in rows],
    }


@router.post("/create")
def create_comm_item(
    payload: CommItemCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    item_type = _normalize_item_type(payload.item_type)
    project_code = _upper(payload.project_code)
    discipline_code = _upper(payload.discipline_code)
    status_code = _upper(payload.status_code) or DEFAULT_STATUS_BY_TYPE[item_type]
    priority = _normalize_priority(payload.priority)
    _enforce_detail_payload_match(item_type=item_type, rfi=payload.rfi, ncr=payload.ncr, tech=payload.tech)

    _require_project_and_discipline(db, project_code, discipline_code)
    _validate_status_exists(db, item_type, status_code)
    enforce_scope_access(db, user, project_code=project_code, discipline_code=discipline_code)

    organization_id = payload.organization_id or getattr(user, "organization_id", None)
    if organization_id:
        _check_optional_org(db, organization_id)
        enforce_organization_access(db, user, organization_id=organization_id)
    for org_id in [payload.recipient_org_id, payload.contractor_org_id, payload.consultant_org_id]:
        _check_optional_org(db, org_id)
        if org_id:
            enforce_organization_access(db, user, organization_id=org_id)
    _check_optional_user(db, payload.assignee_user_id)
    if payload.ncr and payload.ncr.verified_by_id:
        _check_optional_user(db, payload.ncr.verified_by_id)
    if payload.tech and payload.tech.reviewed_by_id:
        _check_optional_user(db, payload.tech.reviewed_by_id)

    item = CommItem(
        item_no=_next_item_no(
            db,
            project_code=project_code,
            item_type=item_type,
            discipline_code=discipline_code,
        ),
        item_type=item_type,
        project_code=project_code,
        discipline_code=discipline_code,
        organization_id=organization_id,
        zone=_norm(payload.zone) or None,
        title=_norm(payload.title),
        short_description=_norm(payload.short_description) or None,
        status_code=status_code,
        priority=priority,
        response_due_date=payload.response_due_date,
        assignee_user_id=payload.assignee_user_id,
        recipient_org_id=payload.recipient_org_id,
        contractor_org_id=payload.contractor_org_id,
        consultant_org_id=payload.consultant_org_id,
        contract_clause_ref=_norm(payload.contract_clause_ref) or None,
        spec_clause_ref=_norm(payload.spec_clause_ref) or None,
        wbs_code=_norm(payload.wbs_code) or None,
        activity_code=_norm(payload.activity_code) or None,
        potential_impact_time=bool(payload.potential_impact_time),
        potential_impact_cost=bool(payload.potential_impact_cost),
        potential_impact_quality=bool(payload.potential_impact_quality),
        potential_impact_safety=bool(payload.potential_impact_safety),
        impact_note=_norm(payload.impact_note) or None,
        delay_days_estimate=payload.delay_days_estimate,
        cost_estimate=payload.cost_estimate,
        claim_notice_required=bool(payload.claim_notice_required),
        notice_deadline=payload.notice_deadline,
        is_superseded=bool(payload.is_superseded),
        superseded_by_item_id=payload.superseded_by_item_id,
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    if item_type == "RFI":
        item.rfi_detail = _create_rfi_detail(payload.rfi)
    elif item_type == "NCR":
        item.ncr_detail = _create_ncr_detail(payload.ncr)
    elif item_type == "TECH":
        item.tech_detail = _create_tech_detail(db, payload.tech)

    if item.superseded_by_item_id:
        target = db.query(CommItem.id).filter(CommItem.id == item.superseded_by_item_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="superseded_by_item_id not found")
        item.is_superseded = True

    db.add(item)
    db.flush()
    _validate_business_rules(item)
    _record_status_log(
        db,
        item_id=item.id,
        from_status_code=None,
        to_status_code=item.status_code,
        changed_by_id=getattr(user, "id", None),
        note="Item created",
    )

    if item.status_code == "SUPERSEDED" and item.superseded_by_item_id:
        relation = ItemRelation(
            from_item_id=item.id,
            to_item_id=item.superseded_by_item_id,
            relation_type="SUPERSEDES",
            note="Auto-linked on create",
            created_by_id=getattr(user, "id", None),
            created_at=datetime.utcnow(),
        )
        db.add(relation)

    db.commit()
    saved = _load_item_or_404(db, item.id)
    return {"ok": True, "data": _serialize_item(saved, include_details=True)}


@router.get("/{item_id}")
def get_comm_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    row = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, row)
    return {"ok": True, "data": _serialize_item(row, include_details=True)}


@router.put("/{item_id}")
def update_comm_item(
    item_id: int,
    payload: CommItemUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)
    changed_by_id = getattr(user, "id", None)
    fields_set = set(getattr(payload, "model_fields_set", set()) or set())
    _enforce_detail_payload_match(item_type=item.item_type, rfi=payload.rfi, ncr=payload.ncr, tech=payload.tech)

    if "project_code" in fields_set and payload.project_code is not None:
        project_code = _upper(payload.project_code)
        _require_project_and_discipline(db, project_code, item.discipline_code)
        enforce_scope_access(db, user, project_code=project_code, discipline_code=item.discipline_code)
        _set_item_field(db, item=item, field_name="project_code", new_value=project_code, changed_by_id=changed_by_id)
    if "discipline_code" in fields_set and payload.discipline_code is not None:
        discipline_code = _upper(payload.discipline_code)
        _require_project_and_discipline(db, item.project_code, discipline_code)
        enforce_scope_access(db, user, project_code=item.project_code, discipline_code=discipline_code)
        _set_item_field(
            db,
            item=item,
            field_name="discipline_code",
            new_value=discipline_code,
            changed_by_id=changed_by_id,
        )
    if "organization_id" in fields_set:
        _check_optional_org(db, payload.organization_id)
        if payload.organization_id:
            enforce_organization_access(db, user, organization_id=payload.organization_id)
        _set_item_field(
            db,
            item=item,
            field_name="organization_id",
            new_value=payload.organization_id,
            changed_by_id=changed_by_id,
        )
    if "zone" in fields_set:
        _set_item_field(db, item=item, field_name="zone", new_value=_norm(payload.zone) or None, changed_by_id=changed_by_id)
    if "title" in fields_set and payload.title is not None:
        _set_item_field(db, item=item, field_name="title", new_value=_norm(payload.title), changed_by_id=changed_by_id)
    if "short_description" in fields_set:
        _set_item_field(
            db,
            item=item,
            field_name="short_description",
            new_value=_norm(payload.short_description) or None,
            changed_by_id=changed_by_id,
        )
    if "priority" in fields_set and payload.priority is not None:
        _set_item_field(
            db,
            item=item,
            field_name="priority",
            new_value=_normalize_priority(payload.priority),
            changed_by_id=changed_by_id,
        )
    if "response_due_date" in fields_set:
        _set_item_field(
            db,
            item=item,
            field_name="response_due_date",
            new_value=payload.response_due_date,
            changed_by_id=changed_by_id,
        )
    if "assignee_user_id" in fields_set:
        _check_optional_user(db, payload.assignee_user_id)
        _set_item_field(
            db,
            item=item,
            field_name="assignee_user_id",
            new_value=payload.assignee_user_id,
            changed_by_id=changed_by_id,
        )
    if "recipient_org_id" in fields_set:
        _check_optional_org(db, payload.recipient_org_id)
        if payload.recipient_org_id:
            enforce_organization_access(db, user, organization_id=payload.recipient_org_id)
        _set_item_field(
            db,
            item=item,
            field_name="recipient_org_id",
            new_value=payload.recipient_org_id,
            changed_by_id=changed_by_id,
        )
    if "contractor_org_id" in fields_set:
        _check_optional_org(db, payload.contractor_org_id)
        if payload.contractor_org_id:
            enforce_organization_access(db, user, organization_id=payload.contractor_org_id)
        _set_item_field(
            db,
            item=item,
            field_name="contractor_org_id",
            new_value=payload.contractor_org_id,
            changed_by_id=changed_by_id,
        )
    if "consultant_org_id" in fields_set:
        _check_optional_org(db, payload.consultant_org_id)
        if payload.consultant_org_id:
            enforce_organization_access(db, user, organization_id=payload.consultant_org_id)
        _set_item_field(
            db,
            item=item,
            field_name="consultant_org_id",
            new_value=payload.consultant_org_id,
            changed_by_id=changed_by_id,
        )
    if "contract_clause_ref" in fields_set:
        _set_item_field(
            db,
            item=item,
            field_name="contract_clause_ref",
            new_value=_norm(payload.contract_clause_ref) or None,
            changed_by_id=changed_by_id,
        )
    if "spec_clause_ref" in fields_set:
        _set_item_field(
            db,
            item=item,
            field_name="spec_clause_ref",
            new_value=_norm(payload.spec_clause_ref) or None,
            changed_by_id=changed_by_id,
        )
    if "wbs_code" in fields_set:
        _set_item_field(db, item=item, field_name="wbs_code", new_value=_norm(payload.wbs_code) or None, changed_by_id=changed_by_id)
    if "activity_code" in fields_set:
        _set_item_field(
            db,
            item=item,
            field_name="activity_code",
            new_value=_norm(payload.activity_code) or None,
            changed_by_id=changed_by_id,
        )
    if "potential_impact_time" in fields_set and payload.potential_impact_time is not None:
        _set_item_field(
            db,
            item=item,
            field_name="potential_impact_time",
            new_value=bool(payload.potential_impact_time),
            changed_by_id=changed_by_id,
        )
    if "potential_impact_cost" in fields_set and payload.potential_impact_cost is not None:
        _set_item_field(
            db,
            item=item,
            field_name="potential_impact_cost",
            new_value=bool(payload.potential_impact_cost),
            changed_by_id=changed_by_id,
        )
    if "potential_impact_quality" in fields_set and payload.potential_impact_quality is not None:
        _set_item_field(
            db,
            item=item,
            field_name="potential_impact_quality",
            new_value=bool(payload.potential_impact_quality),
            changed_by_id=changed_by_id,
        )
    if "potential_impact_safety" in fields_set and payload.potential_impact_safety is not None:
        _set_item_field(
            db,
            item=item,
            field_name="potential_impact_safety",
            new_value=bool(payload.potential_impact_safety),
            changed_by_id=changed_by_id,
        )
    if "impact_note" in fields_set:
        _set_item_field(db, item=item, field_name="impact_note", new_value=_norm(payload.impact_note) or None, changed_by_id=changed_by_id)
    if "delay_days_estimate" in fields_set:
        _set_item_field(
            db,
            item=item,
            field_name="delay_days_estimate",
            new_value=payload.delay_days_estimate,
            changed_by_id=changed_by_id,
        )
    if "cost_estimate" in fields_set:
        _set_item_field(db, item=item, field_name="cost_estimate", new_value=payload.cost_estimate, changed_by_id=changed_by_id)
    if "claim_notice_required" in fields_set and payload.claim_notice_required is not None:
        _set_item_field(
            db,
            item=item,
            field_name="claim_notice_required",
            new_value=bool(payload.claim_notice_required),
            changed_by_id=changed_by_id,
        )
    if "notice_deadline" in fields_set:
        _set_item_field(
            db,
            item=item,
            field_name="notice_deadline",
            new_value=payload.notice_deadline,
            changed_by_id=changed_by_id,
        )
    if "is_superseded" in fields_set and payload.is_superseded is not None:
        _set_item_field(
            db,
            item=item,
            field_name="is_superseded",
            new_value=bool(payload.is_superseded),
            changed_by_id=changed_by_id,
        )
    if "superseded_by_item_id" in fields_set:
        if payload.superseded_by_item_id:
            target = db.query(CommItem.id).filter(CommItem.id == payload.superseded_by_item_id).first()
            if not target:
                raise HTTPException(status_code=404, detail="superseded_by_item_id not found")
        _set_item_field(
            db,
            item=item,
            field_name="superseded_by_item_id",
            new_value=payload.superseded_by_item_id,
            changed_by_id=changed_by_id,
        )

    if item.item_type == "RFI" and payload.rfi is not None:
        if not item.rfi_detail:
            item.rfi_detail = _create_rfi_detail(payload.rfi)
        else:
            _update_rfi_detail(item.rfi_detail, payload.rfi)
    if item.item_type == "NCR" and payload.ncr is not None:
        if payload.ncr.verified_by_id:
            _check_optional_user(db, payload.ncr.verified_by_id)
        if not item.ncr_detail:
            item.ncr_detail = _create_ncr_detail(payload.ncr)
        else:
            _update_ncr_detail(item.ncr_detail, payload.ncr)
    if item.item_type == "TECH" and payload.tech is not None:
        if payload.tech.reviewed_by_id:
            _check_optional_user(db, payload.tech.reviewed_by_id)
        if not item.tech_detail:
            item.tech_detail = _create_tech_detail(db, payload.tech)
        else:
            _update_tech_detail(db, item.tech_detail, payload.tech)

    item.updated_at = datetime.utcnow()
    _validate_business_rules(item)
    db.commit()
    saved = _load_item_or_404(db, item.id)
    return {"ok": True, "data": _serialize_item(saved, include_details=True)}


@router.post("/{item_id}/transition")
def transition_comm_item(
    item_id: int,
    payload: CommItemTransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)

    from_status = _upper(item.status_code)
    to_status = _upper(payload.to_status_code)
    if from_status == to_status:
        raise HTTPException(status_code=400, detail="Item already has this status.")

    _validate_status_exists(db, item.item_type, to_status)
    transition = _validate_transition_exists(db, item.item_type, from_status, to_status)
    _ensure_positive_note_if_required(payload.note, transition)
    if to_status == "REOPENED" and not _norm(payload.note):
        raise HTTPException(status_code=400, detail="NCR REOPENED requires transition note.")

    changed_by_id = getattr(user, "id", None)
    _set_item_field(db, item=item, field_name="status_code", new_value=to_status, changed_by_id=changed_by_id)

    if to_status == "SUPERSEDED":
        superseded_by = payload.superseded_by_item_id or item.superseded_by_item_id
        if not superseded_by:
            raise HTTPException(status_code=400, detail="RFI SUPERSEDED requires superseded_by_item_id.")
        target = db.query(CommItem.id).filter(CommItem.id == superseded_by).first()
        if not target:
            raise HTTPException(status_code=404, detail="superseded_by_item_id not found.")
        _set_item_field(db, item=item, field_name="is_superseded", new_value=True, changed_by_id=changed_by_id)
        _set_item_field(
            db,
            item=item,
            field_name="superseded_by_item_id",
            new_value=int(superseded_by),
            changed_by_id=changed_by_id,
        )
        relation = ItemRelation(
            from_item_id=item.id,
            to_item_id=int(superseded_by),
            relation_type="SUPERSEDES",
            note=_norm(payload.note) or "Auto-linked on supersede transition",
            created_by_id=changed_by_id,
            created_at=datetime.utcnow(),
        )
        db.add(relation)

    item.updated_at = datetime.utcnow()
    _validate_business_rules(item)
    _record_status_log(
        db,
        item_id=item.id,
        from_status_code=from_status,
        to_status_code=to_status,
        changed_by_id=changed_by_id,
        note=_norm(payload.note) or None,
    )
    db.commit()
    saved = _load_item_or_404(db, item.id)
    return {"ok": True, "data": _serialize_item(saved, include_details=True)}


@router.get("/{item_id}/timeline")
def get_comm_item_timeline(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)

    status_logs = (
        db.query(ItemStatusLog)
        .options(joinedload(ItemStatusLog.changed_by))
        .filter(ItemStatusLog.item_id == item_id)
        .order_by(ItemStatusLog.changed_at.desc(), ItemStatusLog.id.desc())
        .all()
    )
    field_audits = (
        db.query(ItemFieldAudit)
        .options(joinedload(ItemFieldAudit.changed_by))
        .filter(ItemFieldAudit.item_id == item_id)
        .order_by(ItemFieldAudit.changed_at.desc(), ItemFieldAudit.id.desc())
        .all()
    )
    return {
        "ok": True,
        "status_logs": [_serialize_status_log(row) for row in status_logs],
        "field_audits": [
            {
                "id": row.id,
                "item_id": row.item_id,
                "field_name": row.field_name,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "changed_by_id": row.changed_by_id,
                "changed_by_name": getattr(getattr(row, "changed_by", None), "full_name", None),
                "changed_at": _to_iso(row.changed_at),
            }
            for row in field_audits
        ],
    }


@router.get("/{item_id}/comments")
def list_comm_item_comments(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)
    rows = (
        db.query(ItemComment)
        .options(joinedload(ItemComment.created_by))
        .filter(ItemComment.item_id == item_id)
        .order_by(ItemComment.created_at.desc(), ItemComment.id.desc())
        .all()
    )
    return {"ok": True, "data": [_serialize_comment(row) for row in rows]}


@router.post("/{item_id}/comments")
def create_comm_item_comment(
    item_id: int,
    payload: CommItemCommentIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)

    row = ItemComment(
        item_id=item_id,
        comment_text=_norm(payload.comment_text),
        comment_type=_norm(payload.comment_type) or "comment",
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_comment(row)}


@router.get("/{item_id}/attachments")
def list_comm_item_attachments(
    item_id: int,
    scope_code: Optional[str] = Query(default=None),
    slot_code: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)
    query = (
        db.query(ItemAttachment)
        .options(joinedload(ItemAttachment.uploaded_by))
        .filter(ItemAttachment.item_id == item_id)
    )
    if scope_code:
        query = query.filter(ItemAttachment.scope_code == _normalize_attachment_scope_code(scope_code))
    if slot_code:
        query = query.filter(ItemAttachment.slot_code == _upper(slot_code))
    rows = query.order_by(ItemAttachment.uploaded_at.desc(), ItemAttachment.id.desc()).all()
    data = [_serialize_attachment(row) for row in rows]

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
        scope: {} for scope in sorted(list(ATTACHMENT_SCOPES))
    }
    default_slot = ATTACHMENT_SLOT_RULES.get(_upper(item.item_type), {}).get("GENERAL", "GENERAL_ATTACHMENT")
    for row in data:
        normalized_scope = _upper(row.get("scope_code")) or "GENERAL"
        normalized_slot = _upper(row.get("slot_code")) or default_slot
        grouped.setdefault(normalized_scope, {})
        grouped[normalized_scope].setdefault(normalized_slot, [])
        grouped[normalized_scope][normalized_slot].append(row)

    return {"ok": True, "data": data, "grouped": grouped}


@router.post("/{item_id}/attachments")
def upload_comm_item_attachment(
    item_id: int,
    file: UploadFile = File(...),
    file_kind: str = Form("attachment"),
    scope_code: str = Form("GENERAL"),
    slot_code: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    normalized_kind = _normalize_attachment_file_kind(file_kind)
    normalized_scope_code = _normalize_attachment_scope_code(scope_code)
    normalized_slot_code = _resolve_attachment_slot_code(item.item_type, normalized_scope_code, slot_code)
    now = datetime.utcnow()
    original_name = safe_name(file.filename)
    unique_name = safe_name(f"{now.strftime('%Y%m%d%H%M%S%f')}_{original_name}")
    folder = _item_storage_dir(db, item, normalized_kind, normalized_scope_code)
    storage_manager = StorageManager(db)
    saved = storage_manager.save_upload_secure(
        file=file,
        destination_folder=str(folder),
        new_name=unique_name,
        file_kind=normalized_kind,
    )

    integrations = get_storage_integrations(db)
    mirror_plan = resolve_mirror_enqueue_plan(integrations)
    mirror_provider = str(mirror_plan.get("provider") or "")
    mirror_status = str(mirror_plan.get("status") or "disabled")
    row = ItemAttachment(
        item_id=item_id,
        file_name=original_name,
        stored_path=str(Path(saved.stored_path)),
        file_kind=normalized_kind,
        scope_code=normalized_scope_code,
        slot_code=normalized_slot_code,
        note=_norm(note) or None,
        mime_type=saved.declared_mime or _norm(file.content_type) or None,
        detected_mime=saved.detected_mime,
        validation_status=saved.validation_status,
        sha256=saved.sha256,
        size_bytes=saved.size_bytes,
        storage_backend="local",
        gdrive_file_id=None,
        mirror_provider=mirror_provider or None,
        mirror_remote_id=None,
        mirror_remote_url=None,
        mirror_status=mirror_status,
        mirror_updated_at=datetime.utcnow(),
        uploaded_by_id=getattr(user, "id", None),
        uploaded_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    if bool(mirror_plan.get("enqueue")):
        enqueue_comm_item_mirror_job(
            db,
            attachment_id=row.id,
            work_package_id=None,
        )
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_attachment(row)}


@router.get("/attachments/{attachment_id}/download")
def download_comm_item_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    row = _load_attachment_or_404(db, attachment_id)
    item = _load_item_or_404(db, row.item_id)
    _enforce_item_scope(db, user, item)
    file_path = Path(row.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(path=str(file_path), filename=row.file_name, media_type=row.mime_type)


@router.delete("/{item_id}/attachments")
def delete_comm_item_attachment(
    item_id: int,
    attachment_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)
    row = _load_attachment_or_404(db, attachment_id)
    if int(row.item_id or 0) != int(item_id):
        raise HTTPException(status_code=400, detail="Attachment does not belong to this item.")
    file_path = Path(row.stored_path)
    db.delete(row)
    db.commit()
    try:
        if file_path.exists():
            os.remove(file_path)
    except Exception:
        pass
    return {"ok": True}


@router.get("/{item_id}/relations")
def list_comm_item_relations(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)
    outgoing = (
        db.query(ItemRelation)
        .options(
            joinedload(ItemRelation.created_by),
            joinedload(ItemRelation.from_item),
            joinedload(ItemRelation.to_item),
        )
        .filter(ItemRelation.from_item_id == item_id)
        .order_by(ItemRelation.created_at.desc(), ItemRelation.id.desc())
        .all()
    )
    incoming = (
        db.query(ItemRelation)
        .options(
            joinedload(ItemRelation.created_by),
            joinedload(ItemRelation.from_item),
            joinedload(ItemRelation.to_item),
        )
        .filter(ItemRelation.to_item_id == item_id)
        .order_by(ItemRelation.created_at.desc(), ItemRelation.id.desc())
        .all()
    )
    return {
        "ok": True,
        "outgoing": [_serialize_relation(row) for row in outgoing],
        "incoming": [_serialize_relation(row) for row in incoming],
    }


@router.post("/{item_id}/relations")
def create_comm_item_relation(
    item_id: int,
    payload: CommItemRelationIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)
    to_item = _load_item_or_404(db, payload.to_item_id)
    _enforce_item_scope(db, user, to_item)
    if int(payload.to_item_id) == int(item_id):
        raise HTTPException(status_code=400, detail="Cannot create relation to the same item.")

    relation_type = _upper(payload.relation_type)
    if relation_type not in RELATION_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported relation_type: {payload.relation_type}")

    existing = (
        db.query(ItemRelation.id)
        .filter(
            ItemRelation.from_item_id == item_id,
            ItemRelation.to_item_id == payload.to_item_id,
            ItemRelation.relation_type == relation_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Relation already exists.")

    row = ItemRelation(
        from_item_id=item_id,
        to_item_id=payload.to_item_id,
        relation_type=relation_type,
        note=_norm(payload.note) or None,
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    row = (
        db.query(ItemRelation)
        .options(
            joinedload(ItemRelation.created_by),
            joinedload(ItemRelation.from_item),
            joinedload(ItemRelation.to_item),
        )
        .filter(ItemRelation.id == row.id)
        .first()
    )
    return {"ok": True, "data": _serialize_relation(row)}


@router.delete("/{item_id}/relations")
def delete_comm_item_relation(
    item_id: int,
    relation_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    item = _load_item_or_404(db, item_id)
    _enforce_item_scope(db, user, item)
    row = _load_relation_or_404(db, relation_id)
    if int(item_id) not in {int(row.from_item_id), int(row.to_item_id)}:
        raise HTTPException(status_code=400, detail="Relation does not belong to this item.")
    db.delete(row)
    db.commit()
    return {"ok": True}


def _apply_report_filters(query, *, project_code: str | None, discipline_code: str | None, item_type: str | None):
    if project_code:
        query = query.filter(CommItem.project_code == _upper(project_code))
    if discipline_code:
        query = query.filter(CommItem.discipline_code == _upper(discipline_code))
    if item_type:
        query = query.filter(CommItem.item_type == _normalize_item_type(item_type))
    return query


@router.get("/reports/aging")
def report_aging(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    item_type: Optional[str] = Query(default=None),
    only_overdue: bool = Query(default=False),
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    now = datetime.utcnow()
    query = _base_items_query(db, user)
    query = _apply_report_filters(query, project_code=project_code, discipline_code=discipline_code, item_type=item_type)
    query = query.filter(_open_status_condition(), CommItem.response_due_date.is_not(None))
    if only_overdue:
        query = query.filter(_overdue_condition(now))
    rows = query.order_by(CommItem.response_due_date.asc(), CommItem.id.asc()).limit(limit).all()
    data = [_serialize_item(row, include_details=False) for row in rows]
    overdue_count = sum(1 for row in rows if _is_overdue(row))
    return {
        "ok": True,
        "count": len(data),
        "summary": {
            "open_with_due": len(data),
            "overdue": overdue_count,
            "on_time": max(0, len(data) - overdue_count),
        },
        "data": data,
    }


@router.get("/reports/cycle-time")
def report_cycle_time(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    item_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    base = _base_items_query(db, user)
    base = _apply_report_filters(base, project_code=project_code, discipline_code=discipline_code, item_type=item_type)

    rfi_rows = (
        base.filter(CommItem.item_type == "RFI")
        .join(RfiDetail, RfiDetail.comm_item_id == CommItem.id)
        .filter(RfiDetail.answered_at.is_not(None))
        .all()
    )
    rfi_cycles = [
        max(0.0, (row.rfi_detail.answered_at - row.created_at).total_seconds() / 86400.0)
        for row in rfi_rows
        if row.rfi_detail and row.rfi_detail.answered_at and row.created_at
    ]

    ncr_rows = base.filter(CommItem.item_type == "NCR").all()
    ncr_ids = [int(row.id) for row in ncr_rows if int(row.id or 0) > 0]
    closed_logs_map: dict[int, datetime] = {}
    if ncr_ids:
        closed_logs = (
            db.query(ItemStatusLog.item_id, func.min(ItemStatusLog.changed_at))
            .filter(
                ItemStatusLog.item_id.in_(ncr_ids),
                ItemStatusLog.to_status_code == "CLOSED",
            )
            .group_by(ItemStatusLog.item_id)
            .all()
        )
        closed_logs_map = {int(item_id): changed_at for item_id, changed_at in closed_logs if changed_at}
    ncr_cycles = [
        max(0.0, (closed_logs_map[row.id] - row.created_at).total_seconds() / 86400.0)
        for row in ncr_rows
        if row.id in closed_logs_map and row.created_at
    ]

    tech_rows = (
        base.filter(CommItem.item_type == "TECH")
        .join(TechDetail, TechDetail.comm_item_id == CommItem.id)
        .filter(
            TechDetail.tech_subtype_code == "SUBMITTAL",
            TechDetail.reviewed_at.is_not(None),
        )
        .all()
    )
    tech_cycles = [
        max(0.0, (row.tech_detail.reviewed_at - row.created_at).total_seconds() / 86400.0)
        for row in tech_rows
        if row.tech_detail and row.tech_detail.reviewed_at and row.created_at
    ]

    def _avg(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    return {
        "ok": True,
        "rfi_answered": {
            "count": len(rfi_cycles),
            "avg_days": _avg(rfi_cycles),
        },
        "ncr_closed": {
            "count": len(ncr_cycles),
            "avg_days": _avg(ncr_cycles),
        },
        "tech_submittal_reviewed": {
            "count": len(tech_cycles),
            "avg_days": _avg(tech_cycles),
        },
    }


def _report_impact_signals(
    *,
    project_code: Optional[str] = None,
    discipline_code: Optional[str] = None,
    item_type: Optional[str] = None,
    include_closed: bool = True,
    limit: int = 1000,
    db: Session,
    user: User,
):
    now = datetime.utcnow()
    query = _base_items_query(db, user)
    query = _apply_report_filters(query, project_code=project_code, discipline_code=discipline_code, item_type=item_type)
    if not include_closed:
        query = query.filter(_open_status_condition())
    query = query.filter(or_(_impact_condition(), _overdue_condition(now)))
    rows = query.order_by(CommItem.created_at.desc(), CommItem.id.desc()).limit(limit).all()
    data = [_serialize_item(row, include_details=False) for row in rows]
    overdue_count = sum(1 for row in rows if _is_overdue(row))
    impact_count = sum(
        1
        for row in rows
        if bool(row.potential_impact_time)
        or bool(row.potential_impact_cost)
        or bool(row.potential_impact_quality)
        or bool(row.potential_impact_safety)
    )
    return {
        "ok": True,
        "count": len(data),
        "summary": {
            "impact_flagged": impact_count,
            "sla_overdue": overdue_count,
        },
        "data": data,
    }


@router.get("/reports/impact-signals")
def report_impact_signals(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    item_type: Optional[str] = Query(default=None),
    include_closed: bool = Query(default=True),
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    return _report_impact_signals(
        project_code=project_code,
        discipline_code=discipline_code,
        item_type=item_type,
        include_closed=include_closed,
        limit=limit,
        db=db,
        user=user,
    )


@router.get("/reports/claim-candidates", deprecated=True)
def report_claim_candidates(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    item_type: Optional[str] = Query(default=None),
    include_closed: bool = Query(default=True),
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    return _report_impact_signals(
        project_code=project_code,
        discipline_code=discipline_code,
        item_type=item_type,
        include_closed=include_closed,
        limit=limit,
        db=db,
        user=user,
    )
