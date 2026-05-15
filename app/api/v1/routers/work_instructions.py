from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import (
    User,
    apply_organization_query_filters,
    apply_scope_query_filters,
    enforce_organization_access,
    enforce_scope_access,
    get_db,
    require_permission,
)
from app.db.models import (
    CommItem,
    Discipline,
    Organization,
    Project,
    ReviewResult,
    User as DbUser,
    WorkInstruction,
    WorkInstructionAttachment,
    WorkInstructionComment,
    WorkInstructionFieldAudit,
    WorkInstructionRelation,
    WorkInstructionSequence,
    WorkInstructionStatusLog,
    WorkflowStatus,
    WorkflowTransition,
)
from app.services.folder_service import safe_name
from app.services.nextcloud_adapter import NextcloudAdapter
from app.services.storage import StorageManager
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import (
    enqueue_work_instruction_mirror_job,
    resolve_mirror_enqueue_plan,
    resolve_nextcloud_runtime,
)


router = APIRouter(prefix="/work-instructions", tags=["Work Instructions"])

WORKFLOW_ITEM_TYPE = "WORK_INSTRUCTION"
DEFAULT_STATUS = "DRAFT"
VALID_PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}
TERMINAL_STATUSES = {"CLOSED"}
REVIEW_STATUSES = {
    "IN_REVIEW",
    "APPROVED",
    "APPROVED_AS_NOTED",
    "REVISE_RESUBMIT",
    "REJECTED",
    "CLOSED",
}
RELATION_TYPES = {"CAUSED_BY", "RESULTS_IN", "REFERENCES", "SUPERSEDES", "LINKED_TO_CLAIM"}
ATTACHMENT_SCOPES = {"GENERAL", "REFERENCE", "RESPONSE"}
ATTACHMENT_SLOT_RULES = {
    "GENERAL": "WORK_INSTRUCTION_GENERAL",
    "REFERENCE": "WORK_INSTRUCTION_REFERENCE",
    "RESPONSE": "WORK_INSTRUCTION_RESPONSE",
}
SENSITIVE_FIELDS = {
    "status_code",
    "response_due_date",
    "assignee_user_id",
    "recipient_org_id",
    "required_action",
    "review_result_code",
}


class WorkInstructionCreateIn(BaseModel):
    project_code: str = Field(..., min_length=1, max_length=50)
    discipline_code: str = Field(..., min_length=1, max_length=20)
    organization_id: Optional[int] = Field(default=None, ge=1)
    zone: Optional[str] = Field(default=None, max_length=128)
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    required_action: Optional[str] = None
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
    potential_impact_time: bool = False
    potential_impact_cost: bool = False
    potential_impact_quality: bool = False
    potential_impact_safety: bool = False
    impact_note: Optional[str] = None
    delay_days_estimate: Optional[int] = None
    cost_estimate: Optional[float] = None
    claim_notice_required: bool = False
    notice_deadline: Optional[datetime] = None


class WorkInstructionUpdateIn(BaseModel):
    project_code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    discipline_code: Optional[str] = Field(default=None, min_length=1, max_length=20)
    organization_id: Optional[int] = Field(default=None, ge=1)
    zone: Optional[str] = Field(default=None, max_length=128)
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = None
    required_action: Optional[str] = None
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
    potential_impact_time: Optional[bool] = None
    potential_impact_cost: Optional[bool] = None
    potential_impact_quality: Optional[bool] = None
    potential_impact_safety: Optional[bool] = None
    impact_note: Optional[str] = None
    delay_days_estimate: Optional[int] = None
    cost_estimate: Optional[float] = None
    claim_notice_required: Optional[bool] = None
    notice_deadline: Optional[datetime] = None


class WorkInstructionTransitionIn(BaseModel):
    to_status_code: str = Field(..., min_length=1, max_length=64)
    note: Optional[str] = None


class WorkInstructionCommentIn(BaseModel):
    comment_text: str = Field(..., min_length=1)
    comment_type: str = Field(default="comment", max_length=32)


class WorkInstructionRelationIn(BaseModel):
    target_type: str = Field(default="work_instruction", max_length=32)
    target_id: int = Field(..., ge=1)
    relation_type: str = Field(..., min_length=1, max_length=64)
    note: Optional[str] = None


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _normalize_priority(value: Optional[str]) -> str:
    priority = _upper(value or "NORMAL")
    priority = {"MEDIUM": "NORMAL", "CRITICAL": "URGENT"}.get(priority, priority)
    if priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {value}")
    return priority


def _is_open(row: WorkInstruction) -> bool:
    return _upper(row.status_code) not in TERMINAL_STATUSES


def _calc_aging_days(row: WorkInstruction) -> int | None:
    if not row.response_due_date or not _is_open(row):
        return None
    return max(0, int((datetime.utcnow() - row.response_due_date).days))


def _is_overdue(row: WorkInstruction) -> bool:
    return bool(row.response_due_date and _is_open(row) and row.response_due_date < datetime.utcnow())


def _require_project_and_discipline(db: Session, project_code: str, discipline_code: str) -> None:
    if not db.query(Project.code).filter(Project.code == project_code).first():
        raise HTTPException(status_code=404, detail="Project not found")
    if not db.query(Discipline.code).filter(Discipline.code == discipline_code).first():
        raise HTTPException(status_code=404, detail="Discipline not found")


def _check_optional_org(db: Session, org_id: int | None) -> None:
    if org_id and not db.query(Organization.id).filter(Organization.id == int(org_id)).first():
        raise HTTPException(status_code=404, detail=f"Organization not found: {org_id}")


def _check_optional_user(db: Session, user_id: int | None) -> None:
    if user_id and not db.query(DbUser.id).filter(DbUser.id == int(user_id)).first():
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")


def _require_review_result_if_provided(db: Session, code: str | None) -> None:
    normalized = _upper(code)
    if not normalized:
        return
    row = db.query(ReviewResult.code).filter(ReviewResult.code == normalized, ReviewResult.is_active.is_(True)).first()
    if not row:
        raise HTTPException(status_code=400, detail=f"Unknown review result: {code}")


def _load_instruction_or_404(db: Session, instruction_id: int) -> WorkInstruction:
    row = (
        db.query(WorkInstruction)
        .options(
            joinedload(WorkInstruction.project),
            joinedload(WorkInstruction.discipline),
            joinedload(WorkInstruction.organization),
            joinedload(WorkInstruction.recipient_org),
            joinedload(WorkInstruction.assignee_user),
            joinedload(WorkInstruction.created_by),
            joinedload(WorkInstruction.reviewed_by),
            joinedload(WorkInstruction.review_result),
        )
        .filter(WorkInstruction.id == int(instruction_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Work instruction not found")
    return row


def _load_attachment_or_404(db: Session, attachment_id: int) -> WorkInstructionAttachment:
    row = db.query(WorkInstructionAttachment).filter(WorkInstructionAttachment.id == int(attachment_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return row


def _load_relation_or_404(db: Session, relation_id: int) -> WorkInstructionRelation:
    row = db.query(WorkInstructionRelation).filter(WorkInstructionRelation.id == int(relation_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Relation not found")
    return row


def _enforce_instruction_scope(db: Session, user: User, row: WorkInstruction) -> None:
    enforce_scope_access(db, user, project_code=row.project_code, discipline_code=row.discipline_code)
    enforce_organization_access(db, user, organization_id=row.organization_id)


def _enforce_mutable(row: WorkInstruction) -> None:
    if bool(row.is_legacy_readonly):
        raise HTTPException(status_code=409, detail="Legacy TECH item is read-only in Work Instructions.")


def _next_instruction_no(db: Session, *, project_code: str, discipline_code: str) -> str:
    pcode = _upper(project_code)
    dcode = _upper(discipline_code)
    seq = (
        db.query(WorkInstructionSequence)
        .filter(
            WorkInstructionSequence.project_code == pcode,
            WorkInstructionSequence.discipline_code == dcode,
        )
        .with_for_update()
        .first()
    )
    if seq:
        value = int(seq.next_value or 1)
        seq.next_value = value + 1
        seq.updated_at = datetime.utcnow()
        return f"{pcode}-TECH-{dcode}-{value:04d}"

    seq = WorkInstructionSequence(
        project_code=pcode,
        discipline_code=dcode,
        next_value=2,
        updated_at=datetime.utcnow(),
    )
    db.add(seq)
    return f"{pcode}-TECH-{dcode}-0001"


def _validate_status_exists(db: Session, status_code: str) -> None:
    row = (
        db.query(WorkflowStatus.id)
        .filter(
            WorkflowStatus.item_type == WORKFLOW_ITEM_TYPE,
            WorkflowStatus.code == status_code,
            WorkflowStatus.is_active.is_(True),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail=f"Unknown work instruction status: {status_code}")


def _validate_transition_exists(db: Session, from_status: str, to_status: str) -> WorkflowTransition:
    row = (
        db.query(WorkflowTransition)
        .filter(
            WorkflowTransition.item_type == WORKFLOW_ITEM_TYPE,
            WorkflowTransition.from_status_code == from_status,
            WorkflowTransition.to_status_code == to_status,
            WorkflowTransition.is_active.is_(True),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=409, detail=f"Invalid transition: {from_status} -> {to_status}")
    return row


def _record_status_log(
    db: Session,
    *,
    instruction_id: int,
    from_status_code: str | None,
    to_status_code: str,
    changed_by_id: int | None,
    note: str | None = None,
) -> None:
    db.add(
        WorkInstructionStatusLog(
            instruction_id=instruction_id,
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
    instruction_id: int,
    field_name: str,
    old_value: Any,
    new_value: Any,
    changed_by_id: int | None,
) -> None:
    db.add(
        WorkInstructionFieldAudit(
            instruction_id=instruction_id,
            field_name=field_name,
            old_value=None if old_value is None else str(old_value),
            new_value=None if new_value is None else str(new_value),
            changed_by_id=changed_by_id,
            changed_at=datetime.utcnow(),
        )
    )


def _set_instruction_field(
    db: Session,
    *,
    row: WorkInstruction,
    field_name: str,
    new_value: Any,
    changed_by_id: int | None,
) -> None:
    old_value = getattr(row, field_name, None)
    if old_value == new_value:
        return
    setattr(row, field_name, new_value)
    if field_name in SENSITIVE_FIELDS:
        _record_field_audit(
            db,
            instruction_id=row.id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            changed_by_id=changed_by_id,
        )


def _validate_business_rules(row: WorkInstruction) -> None:
    status_code = _upper(row.status_code)
    if status_code == "SUBMITTED":
        if not row.recipient_org_id or not row.response_due_date:
            raise HTTPException(status_code=400, detail="Submit requires recipient_org_id and response_due_date.")
        if len(_norm(row.description or row.required_action)) < 10:
            raise HTTPException(status_code=400, detail="Submit requires description or required_action.")
    if row.review_result_code and status_code not in REVIEW_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="review_result_code is only valid in review/approval statuses.",
        )


def _serialize_instruction(row: WorkInstruction, *, include_details: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "instruction_no": row.instruction_no,
        "legacy_comm_item_id": row.legacy_comm_item_id,
        "legacy_subtype": row.legacy_subtype,
        "is_legacy_readonly": bool(row.is_legacy_readonly),
        "project_code": row.project_code,
        "project_name": getattr(getattr(row, "project", None), "name_e", None)
        or getattr(getattr(row, "project", None), "name_p", None),
        "discipline_code": row.discipline_code,
        "discipline_name": getattr(getattr(row, "discipline", None), "name_e", None)
        or getattr(getattr(row, "discipline", None), "name_p", None),
        "organization_id": row.organization_id,
        "sender_org_name": getattr(getattr(row, "organization", None), "name", None),
        "zone": row.zone,
        "title": row.title,
        "description": row.description,
        "required_action": row.required_action,
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
        "document_title": row.document_title,
        "document_no": row.document_no,
        "revision": row.revision,
        "transmittal_no": row.transmittal_no,
        "submission_no": row.submission_no,
        "review_cycle_no": row.review_cycle_no,
        "review_result_code": row.review_result_code,
        "review_result_label": getattr(getattr(row, "review_result", None), "label", None),
        "review_note": row.review_note,
        "reviewed_by_id": row.reviewed_by_id,
        "reviewed_by_name": getattr(getattr(row, "reviewed_by", None), "full_name", None),
        "reviewed_at": _to_iso(row.reviewed_at),
        "potential_impact_time": bool(row.potential_impact_time),
        "potential_impact_cost": bool(row.potential_impact_cost),
        "potential_impact_quality": bool(row.potential_impact_quality),
        "potential_impact_safety": bool(row.potential_impact_safety),
        "impact_note": row.impact_note,
        "delay_days_estimate": row.delay_days_estimate,
        "cost_estimate": row.cost_estimate,
        "claim_notice_required": bool(row.claim_notice_required),
        "notice_deadline": _to_iso(row.notice_deadline),
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
        "aging_days": _calc_aging_days(row),
        "is_overdue": _is_overdue(row),
    }
    if include_details:
        payload["attachment_count"] = len(getattr(row, "attachments", []) or [])
    return payload


def _serialize_status_log(row: WorkInstructionStatusLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "instruction_id": row.instruction_id,
        "from_status_code": row.from_status_code,
        "to_status_code": row.to_status_code,
        "changed_by_id": row.changed_by_id,
        "changed_by_name": getattr(getattr(row, "changed_by", None), "full_name", None),
        "changed_at": _to_iso(row.changed_at),
        "note": row.note,
    }


def _serialize_comment(row: WorkInstructionComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "instruction_id": row.instruction_id,
        "comment_text": row.comment_text,
        "comment_type": row.comment_type,
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "created_at": _to_iso(row.created_at),
    }


def _serialize_attachment(row: WorkInstructionAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "instruction_id": row.instruction_id,
        "legacy_item_attachment_id": row.legacy_item_attachment_id,
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
        "storage_backend": row.storage_backend,
        "gdrive_file_id": row.gdrive_file_id,
        "mirror_provider": row.mirror_provider,
        "mirror_remote_id": row.mirror_remote_id,
        "mirror_remote_url": row.mirror_remote_url,
        "mirror_status": row.mirror_status,
        "mirror_updated_at": _to_iso(row.mirror_updated_at),
        "uploaded_by_id": row.uploaded_by_id,
        "uploaded_by_name": getattr(getattr(row, "uploaded_by", None), "full_name", None),
        "uploaded_at": _to_iso(row.uploaded_at),
        "download_url": f"/api/v1/work-instructions/attachments/{row.id}/download",
    }


def _entity_label(entity_type: str, row: Any) -> dict[str, Any]:
    if entity_type == "work_instruction":
        return {
            "type": "work_instruction",
            "id": getattr(row, "id", None),
            "no": getattr(row, "instruction_no", None),
            "title": getattr(row, "title", None),
        }
    return {
        "type": "comm_item",
        "id": getattr(row, "id", None),
        "no": getattr(row, "item_no", None),
        "title": getattr(row, "title", None),
        "item_type": getattr(row, "item_type", None),
    }


def _serialize_relation(row: WorkInstructionRelation) -> dict[str, Any]:
    from_entity = (
        _entity_label("work_instruction", row.from_instruction)
        if row.from_instruction_id
        else _entity_label("comm_item", row.from_comm_item)
    )
    to_entity = (
        _entity_label("work_instruction", row.to_instruction)
        if row.to_instruction_id
        else _entity_label("comm_item", row.to_comm_item)
    )
    return {
        "id": row.id,
        "from_instruction_id": row.from_instruction_id,
        "from_comm_item_id": row.from_comm_item_id,
        "to_instruction_id": row.to_instruction_id,
        "to_comm_item_id": row.to_comm_item_id,
        "relation_type": row.relation_type,
        "note": row.note,
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "created_at": _to_iso(row.created_at),
        "from": from_entity,
        "to": to_entity,
    }


def _normalize_attachment_file_kind(value: Optional[str]) -> str:
    normalized = _norm(value).lower()
    if normalized in {"pdf", "native", "attachment"}:
        return normalized
    return "attachment"


def _normalize_attachment_scope_code(value: Optional[str]) -> str:
    scope = _upper(value or "GENERAL")
    if scope not in ATTACHMENT_SCOPES:
        raise HTTPException(status_code=400, detail=f"Invalid scope_code: {value}")
    return scope


def _resolve_attachment_slot_code(scope_code: str, slot_code: Optional[str]) -> str:
    normalized_scope = _normalize_attachment_scope_code(scope_code)
    expected = ATTACHMENT_SLOT_RULES[normalized_scope]
    raw_slot = _upper(slot_code)
    if raw_slot and raw_slot != expected:
        raise HTTPException(status_code=400, detail=f"Invalid slot_code `{raw_slot}`. Expected `{expected}`.")
    return expected


def _instruction_storage_dir(db: Session, row: WorkInstruction, file_kind: str, scope_code: str = "GENERAL") -> Path:
    storage_manager = StorageManager(db)
    base = storage_manager.get_correspondence_base_path()
    kind_folder = {"pdf": "PDF", "native": "Native", "attachment": "Attachment"}.get(file_kind, "Attachment")
    scope_folder = {"GENERAL": "General", "REFERENCE": "Reference", "RESPONSE": "Response"}.get(
        _upper(scope_code), "General"
    )
    instruction_no = safe_name(row.instruction_no or f"WI-{row.id}")
    path = base / "work_instructions" / instruction_no / scope_folder / kind_folder
    if not storage_manager._is_webdav_primary_mode():
        path.mkdir(parents=True, exist_ok=True)
    return path


def _nextcloud_adapter_for_webdav(db: Session) -> NextcloudAdapter:
    runtime = resolve_nextcloud_runtime(get_storage_integrations(db))
    if not runtime.get("enabled") or runtime.get("mode") != "webdav":
        raise HTTPException(status_code=503, detail="WebDAV storage not configured.")
    return NextcloudAdapter(
        base_url=str(runtime.get("base_url") or ""),
        username=str(runtime.get("username") or ""),
        app_password=str(runtime.get("app_password") or ""),
        root_path=str(runtime.get("root_path") or ""),
        connect_timeout=float(runtime.get("connect_timeout") or 5),
        read_timeout=float(runtime.get("read_timeout") or 10),
        tls_verify=bool(runtime.get("tls_verify")),
    )


def _download_webdav_attachment(db: Session, row: WorkInstructionAttachment) -> StreamingResponse:
    remote_path = str(row.stored_path or "").strip().replace("webdav://", "", 1)
    adapter = _nextcloud_adapter_for_webdav(db)
    if not adapter.file_exists(remote_path):
        raise HTTPException(status_code=404, detail="Attachment file not found")
    filename = safe_name(row.file_name or f"attachment-{row.id}") or f"attachment-{row.id}"
    media_type = _norm(row.mime_type or row.detected_mime) or "application/octet-stream"
    return StreamingResponse(
        adapter.download_file_stream(remote_path),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _delete_stored_attachment_file(db: Session, stored_path: str) -> None:
    raw_path = _norm(stored_path)
    if not raw_path:
        return
    if raw_path.startswith("webdav://"):
        try:
            _nextcloud_adapter_for_webdav(db).delete_file(raw_path.replace("webdav://", "", 1))
        except Exception:
            pass
        return
    try:
        file_path = Path(raw_path)
        if file_path.exists():
            os.remove(file_path)
    except Exception:
        pass


def _base_query(db: Session, user: User):
    query = db.query(WorkInstruction).options(
        joinedload(WorkInstruction.project),
        joinedload(WorkInstruction.discipline),
        joinedload(WorkInstruction.organization),
        joinedload(WorkInstruction.recipient_org),
        joinedload(WorkInstruction.assignee_user),
        joinedload(WorkInstruction.created_by),
        joinedload(WorkInstruction.review_result),
    )
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=WorkInstruction.project_code,
        discipline_column=WorkInstruction.discipline_code,
    )
    query = apply_organization_query_filters(query, db, user, organization_column=WorkInstruction.organization_id)
    return query


@router.get("/catalog")
def get_work_instruction_catalog(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:read")),
):
    del user
    statuses = (
        db.query(WorkflowStatus)
        .filter(WorkflowStatus.item_type == WORKFLOW_ITEM_TYPE, WorkflowStatus.is_active.is_(True))
        .order_by(WorkflowStatus.sort_order.asc(), WorkflowStatus.id.asc())
        .all()
    )
    transitions = (
        db.query(WorkflowTransition)
        .filter(WorkflowTransition.item_type == WORKFLOW_ITEM_TYPE, WorkflowTransition.is_active.is_(True))
        .order_by(WorkflowTransition.from_status_code.asc(), WorkflowTransition.to_status_code.asc())
        .all()
    )
    projects = db.query(Project).order_by(Project.code.asc()).all()
    disciplines = db.query(Discipline).order_by(Discipline.code.asc()).all()
    organizations = db.query(Organization).order_by(Organization.name.asc(), Organization.id.asc()).all()
    review_results = (
        db.query(ReviewResult)
        .filter(ReviewResult.is_active.is_(True))
        .order_by(ReviewResult.sort_order.asc(), ReviewResult.code.asc())
        .all()
    )
    return {
        "ok": True,
        "priorities": sorted(list(VALID_PRIORITIES)),
        "default_status": DEFAULT_STATUS,
        "legacy_subtypes": ["INSTRUCTION", "IR"],
        "relation_types": sorted(list(RELATION_TYPES)),
        "attachment_scopes": sorted(list(ATTACHMENT_SCOPES)),
        "attachment_slot_rules": ATTACHMENT_SLOT_RULES,
        "workflow_statuses": [
            {
                "code": row.code,
                "label": row.label,
                "is_terminal": bool(row.is_terminal),
                "sort_order": row.sort_order,
            }
            for row in statuses
        ],
        "workflow_transitions": [
            {
                "from_status_code": row.from_status_code,
                "to_status_code": row.to_status_code,
                "requires_note": bool(row.requires_note),
            }
            for row in transitions
        ],
        "projects": [
            {"code": row.code, "name": getattr(row, "name_e", None) or getattr(row, "name_p", None) or row.code}
            for row in projects
        ],
        "disciplines": [
            {"code": row.code, "name": getattr(row, "name_e", None) or getattr(row, "name_p", None) or row.code}
            for row in disciplines
        ],
        "organizations": [
            {"id": row.id, "name": row.name, "code": getattr(row, "code", None), "type": getattr(row, "org_type", None)}
            for row in organizations
        ],
        "review_results": [
            {"code": row.code, "label": row.label, "sort_order": row.sort_order}
            for row in review_results
        ],
    }


@router.get("/list")
def list_work_instructions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: Optional[str] = Query(default=None),
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    recipient_org_id: Optional[int] = Query(default=None, ge=1),
    assignee_user_id: Optional[int] = Query(default=None, ge=1),
    legacy_only: Optional[bool] = Query(default=None),
    editable_only: Optional[bool] = Query(default=None),
    overdue_only: bool = Query(default=False),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:read")),
):
    query = _base_query(db, user)
    if project_code:
        query = query.filter(WorkInstruction.project_code == _upper(project_code))
    if discipline_code:
        query = query.filter(WorkInstruction.discipline_code == _upper(discipline_code))
    if status_code:
        query = query.filter(WorkInstruction.status_code == _upper(status_code))
    if priority:
        query = query.filter(WorkInstruction.priority == _normalize_priority(priority))
    if recipient_org_id:
        query = query.filter(WorkInstruction.recipient_org_id == int(recipient_org_id))
    if assignee_user_id:
        query = query.filter(WorkInstruction.assignee_user_id == int(assignee_user_id))
    if legacy_only is not None:
        query = query.filter(
            WorkInstruction.legacy_comm_item_id.is_not(None) if legacy_only else WorkInstruction.legacy_comm_item_id.is_(None)
        )
    if editable_only:
        query = query.filter(WorkInstruction.is_legacy_readonly.is_(False))
    if overdue_only:
        query = query.filter(
            WorkInstruction.response_due_date.is_not(None),
            WorkInstruction.response_due_date < datetime.utcnow(),
            WorkInstruction.status_code.notin_(list(TERMINAL_STATUSES)),
        )
    if search:
        like_term = f"%{_norm(search)}%"
        query = query.filter(
            or_(
                WorkInstruction.instruction_no.ilike(like_term),
                WorkInstruction.title.ilike(like_term),
                WorkInstruction.description.ilike(like_term),
                WorkInstruction.required_action.ilike(like_term),
                WorkInstruction.document_no.ilike(like_term),
                WorkInstruction.transmittal_no.ilike(like_term),
            )
        )
    total = query.count()
    sort_columns = {
        "instruction_no": WorkInstruction.instruction_no,
        "created_at": WorkInstruction.created_at,
        "updated_at": WorkInstruction.updated_at,
        "response_due_date": WorkInstruction.response_due_date,
        "status_code": WorkInstruction.status_code,
        "priority": WorkInstruction.priority,
        "title": WorkInstruction.title,
    }
    sort_column = sort_columns.get(_norm(sort_by), WorkInstruction.created_at)
    if _norm(sort_dir).lower() == "asc":
        query = query.order_by(sort_column.asc(), WorkInstruction.id.asc())
    else:
        query = query.order_by(sort_column.desc(), WorkInstruction.id.desc())
    rows = query.offset(skip).limit(limit).all()
    return {
        "ok": True,
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [_serialize_instruction(row, include_details=False) for row in rows],
    }


@router.post("/create")
def create_work_instruction(
    payload: WorkInstructionCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:create")),
):
    project_code = _upper(payload.project_code)
    discipline_code = _upper(payload.discipline_code)
    status_code = _upper(payload.status_code) or DEFAULT_STATUS
    priority = _normalize_priority(payload.priority)
    _require_project_and_discipline(db, project_code, discipline_code)
    _validate_status_exists(db, status_code)
    _require_review_result_if_provided(db, payload.review_result_code)
    enforce_scope_access(db, user, project_code=project_code, discipline_code=discipline_code)

    organization_id = payload.organization_id or getattr(user, "organization_id", None)
    for org_id in [
        organization_id,
        payload.recipient_org_id,
        payload.contractor_org_id,
        payload.consultant_org_id,
    ]:
        _check_optional_org(db, org_id)
    if organization_id:
        enforce_organization_access(db, user, organization_id=organization_id)
    _check_optional_user(db, payload.assignee_user_id)
    _check_optional_user(db, payload.reviewed_by_id)

    row = WorkInstruction(
        instruction_no=_next_instruction_no(db, project_code=project_code, discipline_code=discipline_code),
        legacy_subtype="INSTRUCTION",
        is_legacy_readonly=False,
        project_code=project_code,
        discipline_code=discipline_code,
        organization_id=organization_id,
        zone=_norm(payload.zone) or None,
        title=_norm(payload.title),
        description=_norm(payload.description) or None,
        required_action=_norm(payload.required_action) or None,
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
        potential_impact_time=bool(payload.potential_impact_time),
        potential_impact_cost=bool(payload.potential_impact_cost),
        potential_impact_quality=bool(payload.potential_impact_quality),
        potential_impact_safety=bool(payload.potential_impact_safety),
        impact_note=_norm(payload.impact_note) or None,
        delay_days_estimate=payload.delay_days_estimate,
        cost_estimate=payload.cost_estimate,
        claim_notice_required=bool(payload.claim_notice_required),
        notice_deadline=payload.notice_deadline,
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    _validate_business_rules(row)
    _record_status_log(
        db,
        instruction_id=row.id,
        from_status_code=None,
        to_status_code=row.status_code,
        changed_by_id=getattr(user, "id", None),
        note="Work instruction created",
    )
    db.commit()
    return {"ok": True, "data": _serialize_instruction(_load_instruction_or_404(db, row.id))}


@router.get("/{instruction_id}")
def get_work_instruction(
    instruction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:read")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    return {"ok": True, "data": _serialize_instruction(row)}


@router.put("/{instruction_id}")
def update_work_instruction(
    instruction_id: int,
    payload: WorkInstructionUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:update")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    _enforce_mutable(row)
    changed_by_id = getattr(user, "id", None)
    fields_set = set(getattr(payload, "model_fields_set", set()) or set())

    if "project_code" in fields_set and payload.project_code is not None:
        project_code = _upper(payload.project_code)
        _require_project_and_discipline(db, project_code, row.discipline_code)
        enforce_scope_access(db, user, project_code=project_code, discipline_code=row.discipline_code)
        _set_instruction_field(db, row=row, field_name="project_code", new_value=project_code, changed_by_id=changed_by_id)
    if "discipline_code" in fields_set and payload.discipline_code is not None:
        discipline_code = _upper(payload.discipline_code)
        _require_project_and_discipline(db, row.project_code, discipline_code)
        enforce_scope_access(db, user, project_code=row.project_code, discipline_code=discipline_code)
        _set_instruction_field(
            db, row=row, field_name="discipline_code", new_value=discipline_code, changed_by_id=changed_by_id
        )

    scalar_fields = {
        "organization_id": payload.organization_id,
        "zone": _norm(payload.zone) or None,
        "title": _norm(payload.title) if payload.title is not None else None,
        "description": _norm(payload.description) or None,
        "required_action": _norm(payload.required_action) or None,
        "priority": _normalize_priority(payload.priority) if payload.priority is not None else None,
        "response_due_date": payload.response_due_date,
        "assignee_user_id": payload.assignee_user_id,
        "recipient_org_id": payload.recipient_org_id,
        "contractor_org_id": payload.contractor_org_id,
        "consultant_org_id": payload.consultant_org_id,
        "contract_clause_ref": _norm(payload.contract_clause_ref) or None,
        "spec_clause_ref": _norm(payload.spec_clause_ref) or None,
        "wbs_code": _norm(payload.wbs_code) or None,
        "activity_code": _norm(payload.activity_code) or None,
        "document_title": _norm(payload.document_title) or None,
        "document_no": _norm(payload.document_no) or None,
        "revision": _norm(payload.revision) or None,
        "transmittal_no": _norm(payload.transmittal_no) or None,
        "submission_no": _norm(payload.submission_no) or None,
        "review_cycle_no": payload.review_cycle_no,
        "review_result_code": _upper(payload.review_result_code) or None,
        "review_note": _norm(payload.review_note) or None,
        "reviewed_by_id": payload.reviewed_by_id,
        "reviewed_at": payload.reviewed_at,
        "potential_impact_time": bool(payload.potential_impact_time) if payload.potential_impact_time is not None else None,
        "potential_impact_cost": bool(payload.potential_impact_cost) if payload.potential_impact_cost is not None else None,
        "potential_impact_quality": bool(payload.potential_impact_quality) if payload.potential_impact_quality is not None else None,
        "potential_impact_safety": bool(payload.potential_impact_safety) if payload.potential_impact_safety is not None else None,
        "impact_note": _norm(payload.impact_note) or None,
        "delay_days_estimate": payload.delay_days_estimate,
        "cost_estimate": payload.cost_estimate,
        "claim_notice_required": bool(payload.claim_notice_required) if payload.claim_notice_required is not None else None,
        "notice_deadline": payload.notice_deadline,
    }

    for org_field in ["organization_id", "recipient_org_id", "contractor_org_id", "consultant_org_id"]:
        if org_field in fields_set:
            _check_optional_org(db, scalar_fields[org_field])
            if org_field in {"organization_id", "contractor_org_id", "consultant_org_id"} and scalar_fields[org_field]:
                enforce_organization_access(db, user, organization_id=scalar_fields[org_field])
    for user_field in ["assignee_user_id", "reviewed_by_id"]:
        if user_field in fields_set:
            _check_optional_user(db, scalar_fields[user_field])
    if "review_result_code" in fields_set:
        _require_review_result_if_provided(db, payload.review_result_code)

    for field_name, new_value in scalar_fields.items():
        if field_name in fields_set:
            _set_instruction_field(db, row=row, field_name=field_name, new_value=new_value, changed_by_id=changed_by_id)

    row.updated_at = datetime.utcnow()
    _validate_business_rules(row)
    db.commit()
    return {"ok": True, "data": _serialize_instruction(_load_instruction_or_404(db, row.id))}


@router.post("/{instruction_id}/transition")
def transition_work_instruction(
    instruction_id: int,
    payload: WorkInstructionTransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:transition")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    _enforce_mutable(row)
    from_status = _upper(row.status_code)
    to_status = _upper(payload.to_status_code)
    transition = _validate_transition_exists(db, from_status, to_status)
    if transition.requires_note and not _norm(payload.note):
        raise HTTPException(status_code=400, detail="Transition note is required.")
    _set_instruction_field(
        db,
        row=row,
        field_name="status_code",
        new_value=to_status,
        changed_by_id=getattr(user, "id", None),
    )
    row.updated_at = datetime.utcnow()
    _validate_business_rules(row)
    _record_status_log(
        db,
        instruction_id=row.id,
        from_status_code=from_status,
        to_status_code=to_status,
        changed_by_id=getattr(user, "id", None),
        note=_norm(payload.note) or None,
    )
    db.commit()
    return {"ok": True, "data": _serialize_instruction(_load_instruction_or_404(db, row.id))}


@router.get("/{instruction_id}/timeline")
def get_work_instruction_timeline(
    instruction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:read")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    status_logs = (
        db.query(WorkInstructionStatusLog)
        .options(joinedload(WorkInstructionStatusLog.changed_by))
        .filter(WorkInstructionStatusLog.instruction_id == instruction_id)
        .order_by(WorkInstructionStatusLog.changed_at.desc(), WorkInstructionStatusLog.id.desc())
        .all()
    )
    field_audits = (
        db.query(WorkInstructionFieldAudit)
        .options(joinedload(WorkInstructionFieldAudit.changed_by))
        .filter(WorkInstructionFieldAudit.instruction_id == instruction_id)
        .order_by(WorkInstructionFieldAudit.changed_at.desc(), WorkInstructionFieldAudit.id.desc())
        .all()
    )
    return {
        "ok": True,
        "status_logs": [_serialize_status_log(log) for log in status_logs],
        "field_audits": [
            {
                "id": audit.id,
                "instruction_id": audit.instruction_id,
                "field_name": audit.field_name,
                "old_value": audit.old_value,
                "new_value": audit.new_value,
                "changed_by_id": audit.changed_by_id,
                "changed_by_name": getattr(getattr(audit, "changed_by", None), "full_name", None),
                "changed_at": _to_iso(audit.changed_at),
            }
            for audit in field_audits
        ],
    }


@router.get("/{instruction_id}/comments")
def list_work_instruction_comments(
    instruction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:read")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    comments = (
        db.query(WorkInstructionComment)
        .options(joinedload(WorkInstructionComment.created_by))
        .filter(WorkInstructionComment.instruction_id == instruction_id)
        .order_by(WorkInstructionComment.created_at.desc(), WorkInstructionComment.id.desc())
        .all()
    )
    return {"ok": True, "data": [_serialize_comment(comment) for comment in comments]}


@router.post("/{instruction_id}/comments")
def create_work_instruction_comment(
    instruction_id: int,
    payload: WorkInstructionCommentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:comment_create")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    _enforce_mutable(row)
    comment = WorkInstructionComment(
        instruction_id=instruction_id,
        comment_text=_norm(payload.comment_text),
        comment_type=_norm(payload.comment_type) or "comment",
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {"ok": True, "data": _serialize_comment(comment)}


@router.get("/{instruction_id}/attachments")
def list_work_instruction_attachments(
    instruction_id: int,
    scope_code: Optional[str] = Query(default=None),
    slot_code: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:read")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    query = (
        db.query(WorkInstructionAttachment)
        .options(joinedload(WorkInstructionAttachment.uploaded_by))
        .filter(WorkInstructionAttachment.instruction_id == instruction_id)
    )
    if scope_code:
        query = query.filter(WorkInstructionAttachment.scope_code == _normalize_attachment_scope_code(scope_code))
    if slot_code:
        query = query.filter(WorkInstructionAttachment.slot_code == _upper(slot_code))
    rows = query.order_by(WorkInstructionAttachment.uploaded_at.desc(), WorkInstructionAttachment.id.desc()).all()
    data = [_serialize_attachment(attachment) for attachment in rows]
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {scope: {} for scope in sorted(ATTACHMENT_SCOPES)}
    for item in data:
        normalized_scope = _upper(item.get("scope_code")) or "GENERAL"
        normalized_slot = _upper(item.get("slot_code")) or ATTACHMENT_SLOT_RULES[normalized_scope]
        grouped.setdefault(normalized_scope, {})
        grouped[normalized_scope].setdefault(normalized_slot, [])
        grouped[normalized_scope][normalized_slot].append(item)
    return {"ok": True, "data": data, "grouped": grouped}


@router.post("/{instruction_id}/attachments")
def upload_work_instruction_attachment(
    instruction_id: int,
    file: UploadFile = File(...),
    file_kind: str = Form("attachment"),
    scope_code: str = Form("GENERAL"),
    slot_code: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:attachment_upload")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    _enforce_mutable(row)
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required")
    normalized_kind = _normalize_attachment_file_kind(file_kind)
    normalized_scope = _normalize_attachment_scope_code(scope_code)
    normalized_slot = _resolve_attachment_slot_code(normalized_scope, slot_code)
    now = datetime.utcnow()
    original_name = safe_name(file.filename)
    unique_name = safe_name(f"{now.strftime('%Y%m%d%H%M%S%f')}_{original_name}")
    storage_manager = StorageManager(db)

    if storage_manager._is_webdav_primary_mode():
        runtime = resolve_nextcloud_runtime(get_storage_integrations(db))
        root_path = str(runtime.get("root_path") or "")
        corr_base = storage_manager.get_correspondence_webdav_base()
        kind_folder = {"pdf": "PDF", "native": "Native", "attachment": "Attachment"}.get(
            normalized_kind, "Attachment"
        )
        scope_folder = {"GENERAL": "General", "REFERENCE": "Reference", "RESPONSE": "Response"}.get(
            normalized_scope, "General"
        )
        instruction_no = safe_name(row.instruction_no or f"WI-{row.id}")
        absolute_path = f"{corr_base}/work_instructions/{instruction_no}/{scope_folder}/{kind_folder}/{unique_name}"
        relative_path = StorageManager.relativize_webdav_path(absolute_path, root_path)
        saved = storage_manager.save_upload_to_webdav(
            file=file,
            remote_relative_path=relative_path,
            file_kind=normalized_kind,
        )
        stored_path = saved.stored_path
    else:
        folder = _instruction_storage_dir(db, row, normalized_kind, normalized_scope)
        saved = storage_manager.save_upload_secure(
            file=file,
            destination_folder=str(folder),
            new_name=unique_name,
            file_kind=normalized_kind,
        )
        stored_path = str(Path(saved.stored_path))

    mirror_plan = resolve_mirror_enqueue_plan(get_storage_integrations(db))
    attachment = WorkInstructionAttachment(
        instruction_id=instruction_id,
        file_name=original_name,
        stored_path=stored_path,
        file_kind=normalized_kind,
        scope_code=normalized_scope,
        slot_code=normalized_slot,
        note=_norm(note) or None,
        mime_type=saved.declared_mime or _norm(file.content_type) or None,
        detected_mime=saved.detected_mime,
        validation_status=saved.validation_status,
        sha256=saved.sha256,
        size_bytes=saved.size_bytes,
        storage_backend=storage_manager.resolve_storage_backend_for_path(saved.stored_path),
        gdrive_file_id=None,
        mirror_provider=str(mirror_plan.get("provider") or "") or None,
        mirror_remote_id=None,
        mirror_remote_url=None,
        mirror_status=str(mirror_plan.get("status") or "disabled"),
        mirror_updated_at=datetime.utcnow(),
        uploaded_by_id=getattr(user, "id", None),
        uploaded_at=datetime.utcnow(),
    )
    db.add(attachment)
    db.flush()
    if bool(mirror_plan.get("enqueue")):
        enqueue_work_instruction_mirror_job(db, attachment_id=attachment.id, work_package_id=None)
    db.commit()
    db.refresh(attachment)
    return {"ok": True, "data": _serialize_attachment(attachment)}


@router.get("/attachments/{attachment_id}/download")
def download_work_instruction_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:read")),
):
    attachment = _load_attachment_or_404(db, attachment_id)
    row = _load_instruction_or_404(db, attachment.instruction_id)
    _enforce_instruction_scope(db, user, row)
    if str(attachment.stored_path or "").strip().startswith("webdav://"):
        return _download_webdav_attachment(db, attachment)
    file_path = Path(attachment.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(path=str(file_path), filename=attachment.file_name, media_type=attachment.mime_type)


@router.delete("/{instruction_id}/attachments")
def delete_work_instruction_attachment(
    instruction_id: int,
    attachment_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:attachment_delete")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    _enforce_mutable(row)
    attachment = _load_attachment_or_404(db, attachment_id)
    if int(attachment.instruction_id or 0) != int(instruction_id):
        raise HTTPException(status_code=400, detail="Attachment does not belong to this work instruction.")
    db.delete(attachment)
    db.commit()
    _delete_stored_attachment_file(db, str(attachment.stored_path or ""))
    return {"ok": True}


@router.get("/{instruction_id}/relations")
def list_work_instruction_relations(
    instruction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:read")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    options = (
        joinedload(WorkInstructionRelation.created_by),
        joinedload(WorkInstructionRelation.from_instruction),
        joinedload(WorkInstructionRelation.to_instruction),
        joinedload(WorkInstructionRelation.from_comm_item),
        joinedload(WorkInstructionRelation.to_comm_item),
    )
    outgoing = (
        db.query(WorkInstructionRelation)
        .options(*options)
        .filter(WorkInstructionRelation.from_instruction_id == instruction_id)
        .order_by(WorkInstructionRelation.created_at.desc(), WorkInstructionRelation.id.desc())
        .all()
    )
    incoming = (
        db.query(WorkInstructionRelation)
        .options(*options)
        .filter(WorkInstructionRelation.to_instruction_id == instruction_id)
        .order_by(WorkInstructionRelation.created_at.desc(), WorkInstructionRelation.id.desc())
        .all()
    )
    return {
        "ok": True,
        "outgoing": [_serialize_relation(relation) for relation in outgoing],
        "incoming": [_serialize_relation(relation) for relation in incoming],
    }


@router.post("/{instruction_id}/relations")
def create_work_instruction_relation(
    instruction_id: int,
    payload: WorkInstructionRelationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:relation_manage")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    _enforce_mutable(row)
    target_type = _norm(payload.target_type).lower()
    relation_type = _upper(payload.relation_type)
    if relation_type not in RELATION_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported relation_type: {payload.relation_type}")
    if target_type not in {"work_instruction", "comm_item"}:
        raise HTTPException(status_code=400, detail="target_type must be work_instruction or comm_item.")

    to_instruction_id: int | None = None
    to_comm_item_id: int | None = None
    if target_type == "work_instruction":
        if int(payload.target_id) == int(instruction_id):
            raise HTTPException(status_code=400, detail="Cannot create relation to the same work instruction.")
        target = _load_instruction_or_404(db, payload.target_id)
        _enforce_instruction_scope(db, user, target)
        to_instruction_id = int(payload.target_id)
    else:
        target = db.query(CommItem).filter(CommItem.id == int(payload.target_id)).first()
        if not target:
            raise HTTPException(status_code=404, detail="Target comm item not found")
        enforce_scope_access(db, user, project_code=target.project_code, discipline_code=target.discipline_code)
        enforce_organization_access(db, user, organization_id=target.organization_id)
        to_comm_item_id = int(payload.target_id)

    existing = (
        db.query(WorkInstructionRelation.id)
        .filter(
            WorkInstructionRelation.from_instruction_id == instruction_id,
            WorkInstructionRelation.to_instruction_id == to_instruction_id,
            WorkInstructionRelation.to_comm_item_id == to_comm_item_id,
            WorkInstructionRelation.relation_type == relation_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Relation already exists.")

    relation = WorkInstructionRelation(
        from_instruction_id=instruction_id,
        to_instruction_id=to_instruction_id,
        to_comm_item_id=to_comm_item_id,
        relation_type=relation_type,
        note=_norm(payload.note) or None,
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
    )
    db.add(relation)
    db.commit()
    relation = (
        db.query(WorkInstructionRelation)
        .options(
            joinedload(WorkInstructionRelation.created_by),
            joinedload(WorkInstructionRelation.from_instruction),
            joinedload(WorkInstructionRelation.to_instruction),
            joinedload(WorkInstructionRelation.from_comm_item),
            joinedload(WorkInstructionRelation.to_comm_item),
        )
        .filter(WorkInstructionRelation.id == relation.id)
        .first()
    )
    return {"ok": True, "data": _serialize_relation(relation)}


@router.delete("/{instruction_id}/relations")
def delete_work_instruction_relation(
    instruction_id: int,
    relation_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_instructions:relation_manage")),
):
    row = _load_instruction_or_404(db, instruction_id)
    _enforce_instruction_scope(db, user, row)
    _enforce_mutable(row)
    relation = _load_relation_or_404(db, relation_id)
    if int(instruction_id) not in {
        int(relation.from_instruction_id or 0),
        int(relation.to_instruction_id or 0),
    }:
        raise HTTPException(status_code=400, detail="Relation does not belong to this work instruction.")
    db.delete(relation)
    db.commit()
    return {"ok": True}
