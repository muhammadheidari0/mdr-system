from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import (
    User,
    apply_scope_query_filters,
    bulk_check_permissions_for_user,
    get_db,
    require_permission,
)
from app.db.models import (
    CommItem,
    Organization,
    PermitQcPermit,
    SiteLog,
    User as DbUser,
    WorkInstruction,
)


router = APIRouter(prefix="/edms/forms", tags=["EDMS Forms"])

COMM_TERMINAL_BY_TYPE: dict[str, set[str]] = {
    "RFI": {"CLOSED", "SUPERSEDED"},
    "NCR": {"CLOSED"},
}
WORK_INSTRUCTION_TERMINAL_STATUSES = {"CLOSED"}
SITE_LOG_CLOSED_STATUSES = {"VERIFIED", "CLOSED", "APPROVED"}
SITE_LOG_CONTRACTOR_STATUSES = {"DRAFT", "RETURNED"}
PERMIT_CLOSED_STATUSES = {"APPROVED", "REJECTED", "CANCELLED", "CLOSED"}
PERMIT_CONTRACTOR_STATUSES = {"DRAFT", "RETURNED"}
VALID_FORM_TYPES = {"SITE_LOG", "RFI", "NCR", "WORK_INSTRUCTION", "PERMIT_QC"}
VALID_OWNER_SCOPES = {"all", "contractor", "consultant", "closed"}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _lower(value: Any) -> str:
    return _norm(value).lower()


def _to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _active_count(items: Iterable[Any]) -> int:
    total = 0
    for item in items or []:
        if getattr(item, "deleted_at", None) is None:
            total += 1
    return total


def _is_comm_open(row: CommItem) -> bool:
    item_type = _upper(row.item_type)
    return _upper(row.status_code) not in COMM_TERMINAL_BY_TYPE.get(item_type, {"CLOSED"})


def _is_overdue(due_date: datetime | None, *, is_open: bool, now: datetime) -> bool:
    return bool(is_open and due_date is not None and due_date < now)


def _delay_days(due_date: datetime | None, *, is_open: bool, now: datetime) -> int | None:
    if not _is_overdue(due_date, is_open=is_open, now=now):
        return None
    return max(0, int((now - due_date).days))


def _org_scope(org: Organization | None) -> str:
    org_type = _lower(getattr(org, "org_type", None))
    if org_type == "contractor":
        return "contractor"
    if org_type in {"consultant", "dcc", "employer", "system"}:
        return "consultant"
    return ""


def _user_org_scope(user: DbUser | None) -> str:
    return _org_scope(getattr(user, "organization", None))


def _site_log_owner(row: SiteLog) -> tuple[str, str]:
    status = _upper(row.status_code)
    if status in SITE_LOG_CLOSED_STATUSES:
        return "closed", "بسته‌شده"
    if status in SITE_LOG_CONTRACTOR_STATUSES:
        return "contractor", "پیمانکار"
    return "consultant", "مشاور / کنترل"


def _permit_owner(row: PermitQcPermit) -> tuple[str, str]:
    status = _upper(row.status_code)
    if status in PERMIT_CLOSED_STATUSES:
        return "closed", "بسته‌شده"
    if status in PERMIT_CONTRACTOR_STATUSES:
        return "contractor", "پیمانکار"
    return "consultant", "مشاور / کنترل"


def _comm_owner(row: CommItem) -> tuple[str, str]:
    if not _is_comm_open(row):
        return "closed", "بسته‌شده"

    assignee_scope = _user_org_scope(getattr(row, "assignee_user", None))
    if assignee_scope:
        return assignee_scope, getattr(getattr(row, "assignee_user", None), "full_name", None) or (
            "پیمانکار" if assignee_scope == "contractor" else "مشاور / کنترل"
        )

    recipient = getattr(row, "recipient_org", None)
    recipient_scope = _org_scope(recipient)
    if recipient_scope:
        return recipient_scope, getattr(recipient, "name", None) or (
            "پیمانکار" if recipient_scope == "contractor" else "مشاور / کنترل"
        )

    return "consultant", "نامشخص / کنترل"


def _work_instruction_owner(row: WorkInstruction) -> tuple[str, str]:
    if _upper(row.status_code) in WORK_INSTRUCTION_TERMINAL_STATUSES:
        return "closed", "بسته‌شده"

    assignee_scope = _user_org_scope(getattr(row, "assignee_user", None))
    if assignee_scope:
        return assignee_scope, getattr(getattr(row, "assignee_user", None), "full_name", None) or (
            "پیمانکار" if assignee_scope == "contractor" else "مشاور / کنترل"
        )

    recipient = getattr(row, "recipient_org", None)
    recipient_scope = _org_scope(recipient)
    if recipient_scope:
        return recipient_scope, getattr(recipient, "name", None) or (
            "پیمانکار" if recipient_scope == "contractor" else "مشاور / کنترل"
        )

    return "consultant", "مشاور / کنترل"


def _can_open_source(capabilities: dict[str, bool], source_type: str, owner_scope: str, form_type: str) -> dict[str, Any]:
    if source_type == "site_log":
        if owner_scope == "contractor":
            hub, tab = "contractor", "execution"
            module_key = "module_site_logs_contractor:read"
        else:
            hub, tab = "consultant", "inspection"
            module_key = "module_site_logs_consultant:read"
        can_open = bool(capabilities.get("site_logs:read") and capabilities.get(module_key))
        return {"can_open_source": can_open, "target_hub": hub, "target_tab": tab}

    if source_type == "comm_item":
        if owner_scope == "contractor":
            hub, tab = "contractor", "requests"
            module_key = "module_comm_items_contractor:read"
        else:
            hub = "consultant"
            tab = "defects" if _upper(form_type) == "NCR" else "control"
            module_key = "module_comm_items_consultant:read"
        can_open = bool(capabilities.get("comm_items:read") and capabilities.get(module_key))
        return {"can_open_source": can_open, "target_hub": hub, "target_tab": tab}

    if source_type == "work_instruction":
        can_open = bool(
            capabilities.get("work_instructions:read")
            and capabilities.get("module_work_instructions_consultant:read")
        )
        return {"can_open_source": can_open, "target_hub": "consultant", "target_tab": "instructions"}

    if source_type == "permit_qc":
        if owner_scope == "contractor":
            hub = "contractor"
            module_key = "module_permit_qc_contractor:read"
        else:
            hub = "consultant"
            module_key = "module_permit_qc_consultant:read"
        can_open = bool(capabilities.get("permit_qc:read") and capabilities.get(module_key))
        return {"can_open_source": can_open, "target_hub": hub, "target_tab": "permit-qc"}

    return {"can_open_source": False, "target_hub": None, "target_tab": None}


def _base_row(
    *,
    source_type: str,
    source_id: int,
    form_type: str,
    number: str | None,
    title: str | None,
    project_code: str | None,
    discipline_code: str | None,
    status_code: str | None,
    owner_scope: str,
    owner_label: str,
    organization_name: str | None,
    record_date: datetime | None,
    due_date: datetime | None,
    is_open: bool,
    attachment_count: int,
    action_count: int,
    capabilities: dict[str, bool],
    now: datetime,
) -> dict[str, Any]:
    source = _can_open_source(capabilities, source_type, owner_scope, form_type)
    return {
        "source_type": source_type,
        "source_id": int(source_id or 0),
        "form_type": form_type,
        "number": number,
        "title": title,
        "project_code": project_code,
        "discipline_code": discipline_code,
        "status_code": status_code,
        "owner_scope": owner_scope,
        "owner_label": owner_label,
        "organization_name": organization_name,
        "record_date": _to_iso(record_date),
        "due_date": _to_iso(due_date),
        "is_open": bool(is_open),
        "is_overdue": _is_overdue(due_date, is_open=is_open, now=now),
        "delay_days": _delay_days(due_date, is_open=is_open, now=now),
        "attachment_count": int(attachment_count or 0),
        "action_count": int(action_count or 0),
        **source,
    }


def _record_sort_value(row: dict[str, Any]) -> str:
    return str(row.get("record_date") or row.get("due_date") or "")


def _matches_filters(
    row: dict[str, Any],
    *,
    form_type: str,
    status_code: str,
    owner_scope: str,
    overdue_only: bool,
) -> bool:
    if form_type and _upper(row.get("form_type")) != form_type:
        return False
    if status_code and _upper(row.get("status_code")) != status_code:
        return False
    if owner_scope != "all" and _lower(row.get("owner_scope")) != owner_scope:
        return False
    if overdue_only and not bool(row.get("is_overdue")):
        return False
    return True


@router.get("/list")
def list_edms_forms(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: Optional[str] = Query(default=None),
    form_type: Optional[str] = Query(default=None),
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    owner_scope: str = Query(default="all"),
    overdue_only: bool = Query(default=False),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("edms_forms:read")),
):
    normalized_form_type = _upper(form_type)
    if normalized_form_type and normalized_form_type not in VALID_FORM_TYPES:
        return {"ok": True, "total": 0, "count": 0, "skip": skip, "limit": limit, "summary": {}, "data": []}

    normalized_owner = _lower(owner_scope) or "all"
    if normalized_owner not in VALID_OWNER_SCOPES:
        normalized_owner = "all"

    normalized_project = _upper(project_code)
    normalized_discipline = _upper(discipline_code)
    normalized_status = _upper(status_code)
    search_term = _norm(search)
    now = datetime.utcnow()
    capabilities = bulk_check_permissions_for_user(
        db,
        user,
        [
            "site_logs:read",
            "module_site_logs_contractor:read",
            "module_site_logs_consultant:read",
            "comm_items:read",
            "module_comm_items_contractor:read",
            "module_comm_items_consultant:read",
            "work_instructions:read",
            "module_work_instructions_consultant:read",
            "permit_qc:read",
            "module_permit_qc_contractor:read",
            "module_permit_qc_consultant:read",
        ],
    )

    rows: list[dict[str, Any]] = []

    if not normalized_form_type or normalized_form_type == "SITE_LOG":
        query = db.query(SiteLog).options(
            joinedload(SiteLog.organization),
            joinedload(SiteLog.attachments),
            joinedload(SiteLog.issue_rows),
        )
        query = apply_scope_query_filters(
            query,
            db,
            user,
            project_column=SiteLog.project_code,
            discipline_column=SiteLog.discipline_code,
        )
        if normalized_project:
            query = query.filter(SiteLog.project_code == normalized_project)
        if normalized_discipline:
            query = query.filter(SiteLog.discipline_code == normalized_discipline)
        if normalized_status:
            query = query.filter(SiteLog.status_code == normalized_status)
        if date_from:
            query = query.filter(SiteLog.log_date >= date_from)
        if date_to:
            query = query.filter(SiteLog.log_date <= date_to)
        if search_term:
            pattern = f"%{search_term}%"
            query = query.filter(
                or_(
                    SiteLog.log_no.ilike(pattern),
                    SiteLog.summary.ilike(pattern),
                    SiteLog.current_work_summary.ilike(pattern),
                    SiteLog.next_plan_summary.ilike(pattern),
                    SiteLog.contract_subject.ilike(pattern),
                    SiteLog.contract_number.ilike(pattern),
                )
            )
        for item in query.all():
            owner, owner_label = _site_log_owner(item)
            title = item.summary or item.current_work_summary or item.contract_subject or item.next_plan_summary
            rows.append(
                _base_row(
                    source_type="site_log",
                    source_id=int(item.id or 0),
                    form_type="SITE_LOG",
                    number=item.log_no,
                    title=title,
                    project_code=item.project_code,
                    discipline_code=item.discipline_code,
                    status_code=item.status_code,
                    owner_scope=owner,
                    owner_label=owner_label,
                    organization_name=getattr(getattr(item, "organization", None), "name", None),
                    record_date=item.log_date,
                    due_date=None,
                    is_open=owner != "closed",
                    attachment_count=_active_count(getattr(item, "attachments", [])),
                    action_count=len(getattr(item, "issue_rows", []) or []),
                    capabilities=capabilities,
                    now=now,
                )
            )

    if not normalized_form_type or normalized_form_type in {"RFI", "NCR"}:
        query = db.query(CommItem).options(
            joinedload(CommItem.organization),
            joinedload(CommItem.recipient_org),
            joinedload(CommItem.assignee_user).joinedload(DbUser.organization),
            joinedload(CommItem.attachments),
            joinedload(CommItem.comments),
        )
        query = apply_scope_query_filters(
            query,
            db,
            user,
            project_column=CommItem.project_code,
            discipline_column=CommItem.discipline_code,
        )
        if normalized_project:
            query = query.filter(CommItem.project_code == normalized_project)
        if normalized_discipline:
            query = query.filter(CommItem.discipline_code == normalized_discipline)
        query = query.filter(CommItem.item_type.in_(["RFI", "NCR"]))
        if normalized_form_type in {"RFI", "NCR"}:
            query = query.filter(CommItem.item_type == normalized_form_type)
        if normalized_status:
            query = query.filter(CommItem.status_code == normalized_status)
        if date_from:
            query = query.filter(CommItem.created_at >= date_from)
        if date_to:
            query = query.filter(CommItem.created_at <= date_to)
        if search_term:
            pattern = f"%{search_term}%"
            query = query.filter(
                or_(
                    CommItem.item_no.ilike(pattern),
                    CommItem.title.ilike(pattern),
                    CommItem.short_description.ilike(pattern),
                )
            )
        for item in query.all():
            owner, owner_label = _comm_owner(item)
            is_open = _is_comm_open(item)
            rows.append(
                _base_row(
                    source_type="comm_item",
                    source_id=int(item.id or 0),
                    form_type=_upper(item.item_type),
                    number=item.item_no,
                    title=item.title or item.short_description,
                    project_code=item.project_code,
                    discipline_code=item.discipline_code,
                    status_code=item.status_code,
                    owner_scope=owner,
                    owner_label=owner_label,
                    organization_name=getattr(getattr(item, "organization", None), "name", None),
                    record_date=item.created_at,
                    due_date=item.response_due_date,
                    is_open=is_open,
                    attachment_count=_active_count(getattr(item, "attachments", [])),
                    action_count=len(getattr(item, "comments", []) or []),
                    capabilities=capabilities,
                    now=now,
                )
            )

    if not normalized_form_type or normalized_form_type == "WORK_INSTRUCTION":
        query = db.query(WorkInstruction).options(
            joinedload(WorkInstruction.organization),
            joinedload(WorkInstruction.recipient_org),
            joinedload(WorkInstruction.assignee_user).joinedload(DbUser.organization),
            joinedload(WorkInstruction.attachments),
            joinedload(WorkInstruction.comments),
        )
        query = apply_scope_query_filters(
            query,
            db,
            user,
            project_column=WorkInstruction.project_code,
            discipline_column=WorkInstruction.discipline_code,
        )
        if normalized_project:
            query = query.filter(WorkInstruction.project_code == normalized_project)
        if normalized_discipline:
            query = query.filter(WorkInstruction.discipline_code == normalized_discipline)
        if normalized_status:
            query = query.filter(WorkInstruction.status_code == normalized_status)
        if date_from:
            query = query.filter(WorkInstruction.created_at >= date_from)
        if date_to:
            query = query.filter(WorkInstruction.created_at <= date_to)
        if search_term:
            pattern = f"%{search_term}%"
            query = query.filter(
                or_(
                    WorkInstruction.instruction_no.ilike(pattern),
                    WorkInstruction.title.ilike(pattern),
                    WorkInstruction.description.ilike(pattern),
                    WorkInstruction.required_action.ilike(pattern),
                    WorkInstruction.document_no.ilike(pattern),
                )
            )
        for item in query.all():
            owner, owner_label = _work_instruction_owner(item)
            is_open = _upper(item.status_code) not in WORK_INSTRUCTION_TERMINAL_STATUSES
            rows.append(
                _base_row(
                    source_type="work_instruction",
                    source_id=int(item.id or 0),
                    form_type="WORK_INSTRUCTION",
                    number=item.instruction_no,
                    title=item.title or item.description,
                    project_code=item.project_code,
                    discipline_code=item.discipline_code,
                    status_code=item.status_code,
                    owner_scope=owner,
                    owner_label=owner_label,
                    organization_name=getattr(getattr(item, "organization", None), "name", None),
                    record_date=item.created_at,
                    due_date=item.response_due_date,
                    is_open=is_open,
                    attachment_count=_active_count(getattr(item, "attachments", [])),
                    action_count=len(getattr(item, "comments", []) or []),
                    capabilities=capabilities,
                    now=now,
                )
            )

    if not normalized_form_type or normalized_form_type == "PERMIT_QC":
        query = db.query(PermitQcPermit).options(
            joinedload(PermitQcPermit.organization),
            joinedload(PermitQcPermit.contractor_org),
            joinedload(PermitQcPermit.consultant_org),
            joinedload(PermitQcPermit.attachments),
            joinedload(PermitQcPermit.stations),
        )
        query = apply_scope_query_filters(
            query,
            db,
            user,
            project_column=PermitQcPermit.project_code,
            discipline_column=PermitQcPermit.discipline_code,
        )
        if normalized_project:
            query = query.filter(PermitQcPermit.project_code == normalized_project)
        if normalized_discipline:
            query = query.filter(PermitQcPermit.discipline_code == normalized_discipline)
        if normalized_status:
            query = query.filter(PermitQcPermit.status_code == normalized_status)
        if date_from:
            query = query.filter(PermitQcPermit.permit_date >= date_from)
        if date_to:
            query = query.filter(PermitQcPermit.permit_date <= date_to)
        if search_term:
            pattern = f"%{search_term}%"
            query = query.filter(
                or_(
                    PermitQcPermit.permit_no.ilike(pattern),
                    PermitQcPermit.title.ilike(pattern),
                    PermitQcPermit.description.ilike(pattern),
                )
            )
        for item in query.all():
            owner, owner_label = _permit_owner(item)
            required_open = sum(
                1
                for station in getattr(item, "stations", []) or []
                if getattr(station, "is_required", False) and _upper(getattr(station, "status_code", None)) != "APPROVED"
            )
            org_name = (
                getattr(getattr(item, "contractor_org", None), "name", None)
                or getattr(getattr(item, "organization", None), "name", None)
                or getattr(getattr(item, "consultant_org", None), "name", None)
            )
            rows.append(
                _base_row(
                    source_type="permit_qc",
                    source_id=int(item.id or 0),
                    form_type="PERMIT_QC",
                    number=item.permit_no,
                    title=item.title,
                    project_code=item.project_code,
                    discipline_code=item.discipline_code,
                    status_code=item.status_code,
                    owner_scope=owner,
                    owner_label=owner_label,
                    organization_name=org_name,
                    record_date=item.permit_date or item.created_at,
                    due_date=None,
                    is_open=owner != "closed",
                    attachment_count=_active_count(getattr(item, "attachments", [])),
                    action_count=required_open,
                    capabilities=capabilities,
                    now=now,
                )
            )

    rows = [
        row
        for row in rows
        if _matches_filters(
            row,
            form_type=normalized_form_type,
            status_code=normalized_status,
            owner_scope=normalized_owner,
            overdue_only=overdue_only,
        )
    ]
    rows.sort(key=_record_sort_value, reverse=True)

    total = len(rows)
    page_rows = rows[skip : skip + limit]
    by_type: dict[str, int] = {}
    for row in rows:
        key = _upper(row.get("form_type"))
        by_type[key] = by_type.get(key, 0) + 1

    summary = {
        "total": total,
        "open": sum(1 for row in rows if bool(row.get("is_open"))),
        "overdue": sum(1 for row in rows if bool(row.get("is_overdue"))),
        "contractor": sum(1 for row in rows if row.get("owner_scope") == "contractor"),
        "consultant": sum(1 for row in rows if row.get("owner_scope") == "consultant"),
        "closed": sum(1 for row in rows if row.get("owner_scope") == "closed"),
        "by_type": by_type,
    }
    return {
        "ok": True,
        "total": total,
        "count": len(page_rows),
        "skip": skip,
        "limit": limit,
        "summary": summary,
        "data": page_rows,
    }
