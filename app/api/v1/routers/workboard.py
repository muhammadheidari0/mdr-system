from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import (
    User,
    allow_editor,
    allow_viewer,
    apply_scope_query_filters,
    enforce_scope_access,
    get_db,
)
from app.db.models import Discipline, Project, WorkboardItem

router = APIRouter(prefix="/workboard", tags=["Workboard"])

VALID_MODULE_TABS: dict[str, set[str]] = {
    "contractor": {"execution", "requests", "quality", "reports"},
    "consultant": {"inspection", "defects", "instructions", "control"},
}

VALID_STATUSES = {"open", "in_progress", "waiting", "done", "blocked"}
VALID_PRIORITIES = {"low", "normal", "high", "urgent"}


def _norm(value: Optional[str]) -> str:
    return str(value or "").strip()


def _norm_lower(value: Optional[str]) -> str:
    return _norm(value).lower()


def _norm_upper(value: Optional[str]) -> str:
    return _norm(value).upper()


def _validate_module_tab(module_key: str, tab_key: str) -> tuple[str, str]:
    module = _norm_lower(module_key)
    tab = _norm_lower(tab_key)
    allowed_tabs = VALID_MODULE_TABS.get(module)
    if not allowed_tabs:
        raise HTTPException(status_code=400, detail=f"Invalid module_key: {module_key}")
    if tab not in allowed_tabs:
        raise HTTPException(status_code=400, detail=f"Invalid tab_key `{tab_key}` for module `{module}`")
    return module, tab


def _normalize_status(value: Optional[str]) -> str:
    raw = _norm_lower(value)
    aliases = {
        "inprogress": "in_progress",
        "wip": "in_progress",
        "pending": "waiting",
        "closed": "done",
        "completed": "done",
    }
    status = aliases.get(raw, raw or "open")
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {value}")
    return status


def _normalize_priority(value: Optional[str]) -> str:
    raw = _norm_lower(value)
    aliases = {
        "medium": "normal",
        "critical": "urgent",
    }
    priority = aliases.get(raw, raw or "normal")
    if priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {value}")
    return priority


def _serialize_item(row: WorkboardItem) -> dict:
    return {
        "id": row.id,
        "module_key": row.module_key,
        "tab_key": row.tab_key,
        "project_code": row.project_code,
        "project_name": getattr(getattr(row, "project", None), "name_e", None)
        or getattr(getattr(row, "project", None), "name_p", None),
        "discipline_code": row.discipline_code,
        "discipline_name": getattr(getattr(row, "discipline", None), "name_e", None)
        or getattr(getattr(row, "discipline", None), "name_p", None),
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "priority": row.priority,
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "updated_by_id": row.updated_by_id,
        "updated_by_name": getattr(getattr(row, "updated_by", None), "full_name", None),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _require_project_if_provided(db: Session, project_code: Optional[str]) -> Optional[str]:
    value = _norm_upper(project_code) or None
    if not value:
        return None
    row = db.query(Project).filter(Project.code == value).first()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return value


def _require_discipline_if_provided(db: Session, discipline_code: Optional[str]) -> Optional[str]:
    value = _norm_upper(discipline_code) or None
    if not value:
        return None
    row = db.query(Discipline).filter(Discipline.code == value).first()
    if not row:
        raise HTTPException(status_code=404, detail="Discipline not found")
    return value


def _load_item_or_404(db: Session, item_id: int) -> WorkboardItem:
    row = (
        db.query(WorkboardItem)
        .options(
            joinedload(WorkboardItem.project),
            joinedload(WorkboardItem.discipline),
            joinedload(WorkboardItem.created_by),
            joinedload(WorkboardItem.updated_by),
        )
        .filter(WorkboardItem.id == item_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Workboard item not found")
    return row


class WorkboardCreateIn(BaseModel):
    module_key: str = Field(..., min_length=1, max_length=32)
    tab_key: str = Field(..., min_length=1, max_length=32)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    project_code: Optional[str] = Field(default=None, max_length=50)
    discipline_code: Optional[str] = Field(default=None, max_length=20)
    status: str = Field(default="open", max_length=32)
    priority: str = Field(default="normal", max_length=32)
    due_date: Optional[datetime] = None


class WorkboardUpdateIn(BaseModel):
    module_key: Optional[str] = Field(default=None, max_length=32)
    tab_key: Optional[str] = Field(default=None, max_length=32)
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    project_code: Optional[str] = Field(default=None, max_length=50)
    discipline_code: Optional[str] = Field(default=None, max_length=20)
    status: Optional[str] = Field(default=None, max_length=32)
    priority: Optional[str] = Field(default=None, max_length=32)
    due_date: Optional[datetime] = None


@router.get("/catalog")
def get_workboard_catalog(
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    del user
    return {
        "ok": True,
        "modules": [
            {"key": module_key, "tabs": sorted(list(tab_keys))}
            for module_key, tab_keys in VALID_MODULE_TABS.items()
        ],
        "statuses": sorted(list(VALID_STATUSES)),
        "priorities": sorted(list(VALID_PRIORITIES)),
    }


@router.get("/summary")
def get_workboard_summary(
    module_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    query = db.query(WorkboardItem)
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=WorkboardItem.project_code,
        discipline_column=WorkboardItem.discipline_code,
    )

    module_value = _norm_lower(module_key)
    if module_value:
        if module_value not in VALID_MODULE_TABS:
            raise HTTPException(status_code=400, detail=f"Invalid module_key: {module_key}")
        query = query.filter(WorkboardItem.module_key == module_value)

    rows = query.all()
    now = datetime.utcnow()
    today = now.date()
    stats = {
        "total": 0,
        "open": 0,
        "in_progress": 0,
        "waiting": 0,
        "done": 0,
        "blocked": 0,
        "overdue": 0,
        "due_today": 0,
        "by_tab": {},
    }
    for row in rows:
        stats["total"] += 1
        status = _norm_lower(row.status) or "open"
        if status in VALID_STATUSES:
            stats[status] += 1
        if row.due_date and status != "done":
            due_date = row.due_date.date()
            if due_date < today:
                stats["overdue"] += 1
            elif due_date == today:
                stats["due_today"] += 1
        tab_key = str(row.tab_key or "").strip().lower()
        if tab_key:
            stats["by_tab"][tab_key] = stats["by_tab"].get(tab_key, 0) + 1

    return {"ok": True, "stats": stats}


@router.get("/list")
def list_workboard_items(
    module_key: str = Query(..., min_length=1),
    tab_key: str = Query(..., min_length=1),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    module_value, tab_value = _validate_module_tab(module_key, tab_key)
    query = (
        db.query(WorkboardItem)
        .options(
            joinedload(WorkboardItem.project),
            joinedload(WorkboardItem.discipline),
            joinedload(WorkboardItem.created_by),
            joinedload(WorkboardItem.updated_by),
        )
        .filter(
            WorkboardItem.module_key == module_value,
            WorkboardItem.tab_key == tab_value,
        )
    )
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=WorkboardItem.project_code,
        discipline_column=WorkboardItem.discipline_code,
    )

    search_value = _norm(search)
    if search_value:
        pattern = f"%{search_value}%"
        query = query.filter(
            or_(
                WorkboardItem.title.ilike(pattern),
                WorkboardItem.description.ilike(pattern),
            )
        )

    status_value = _norm_lower(status)
    if status_value:
        status_value = _normalize_status(status_value)
        query = query.filter(WorkboardItem.status == status_value)

    priority_value = _norm_lower(priority)
    if priority_value:
        priority_value = _normalize_priority(priority_value)
        query = query.filter(WorkboardItem.priority == priority_value)

    project_value = _norm_upper(project_code)
    if project_value:
        enforce_scope_access(db, user, project_code=project_value)
        query = query.filter(WorkboardItem.project_code == project_value)

    discipline_value = _norm_upper(discipline_code)
    if discipline_value:
        enforce_scope_access(db, user, discipline_code=discipline_value)
        query = query.filter(WorkboardItem.discipline_code == discipline_value)

    total = query.count()
    rows = (
        query.order_by(
            WorkboardItem.updated_at.desc(),
            WorkboardItem.id.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "ok": True,
        "total": total,
        "data": [_serialize_item(row) for row in rows],
    }


@router.post("/create")
def create_workboard_item(
    payload: WorkboardCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    module_value, tab_value = _validate_module_tab(payload.module_key, payload.tab_key)
    title = _norm(payload.title)
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    project_code = _require_project_if_provided(db, payload.project_code)
    discipline_code = _require_discipline_if_provided(db, payload.discipline_code)
    enforce_scope_access(
        db,
        user,
        project_code=project_code,
        discipline_code=discipline_code,
    )

    row = WorkboardItem(
        module_key=module_value,
        tab_key=tab_value,
        project_code=project_code,
        discipline_code=discipline_code,
        title=title,
        description=_norm(payload.description) or None,
        status=_normalize_status(payload.status),
        priority=_normalize_priority(payload.priority),
        due_date=payload.due_date,
        created_by_id=getattr(user, "id", None),
        updated_by_id=getattr(user, "id", None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    row = _load_item_or_404(db, row.id)
    return {"ok": True, "data": _serialize_item(row)}


@router.put("/{item_id}")
def update_workboard_item(
    item_id: int,
    payload: WorkboardUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    row = _load_item_or_404(db, item_id)
    enforce_scope_access(
        db,
        user,
        project_code=row.project_code,
        discipline_code=row.discipline_code,
    )
    provided = set(payload.model_fields_set)

    if "module_key" in provided or "tab_key" in provided:
        module_value = payload.module_key if payload.module_key is not None else row.module_key
        tab_value = payload.tab_key if payload.tab_key is not None else row.tab_key
        module_value, tab_value = _validate_module_tab(module_value, tab_value)
        row.module_key = module_value
        row.tab_key = tab_value

    if "project_code" in provided:
        row.project_code = _require_project_if_provided(db, payload.project_code)
    if "discipline_code" in provided:
        row.discipline_code = _require_discipline_if_provided(db, payload.discipline_code)

    if "title" in provided:
        title = _norm(payload.title)
        if not title:
            raise HTTPException(status_code=400, detail="title cannot be empty")
        row.title = title

    if "description" in provided:
        row.description = _norm(payload.description) or None

    if "status" in provided:
        row.status = _normalize_status(payload.status)
    if "priority" in provided:
        row.priority = _normalize_priority(payload.priority)
    if "due_date" in provided:
        row.due_date = payload.due_date

    enforce_scope_access(
        db,
        user,
        project_code=row.project_code,
        discipline_code=row.discipline_code,
    )

    row.updated_by_id = getattr(user, "id", None)
    db.commit()
    row = _load_item_or_404(db, row.id)
    return {"ok": True, "data": _serialize_item(row)}


@router.delete("/{item_id}")
def delete_workboard_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    row = _load_item_or_404(db, item_id)
    enforce_scope_access(
        db,
        user,
        project_code=row.project_code,
        discipline_code=row.discipline_code,
    )
    db.delete(row)
    db.commit()
    return {"ok": True}
