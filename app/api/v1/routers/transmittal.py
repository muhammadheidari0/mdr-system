from datetime import datetime
from types import SimpleNamespace
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.api.dependencies import (
    User,
    apply_scope_query_filters,
    enforce_scope_access,
    get_db,
    require_permission,
)
from app.db.models import (
    DocumentRevision,
    MdrDocument,
    Transmittal,
    TransmittalDoc,
)
from app.services.pdf_service import generate_transmittal_pdf

router = APIRouter(prefix="/transmittal", tags=["Transmittal"])
STATE_DRAFT = "draft"
STATE_ISSUED = "issued"
STATE_VOID = "void"
EDITABLE_STATES = {STATE_DRAFT}
VOIDABLE_STATES = {STATE_DRAFT, STATE_ISSUED}


class TransmittalDocItem(BaseModel):
    document_code: str
    revision: str
    status: str
    electronic_copy: bool = True
    hard_copy: bool = False


class TransmittalCreate(BaseModel):
    project_code: str
    sender: str
    receiver: str
    subject: Optional[str] = None
    notes: Optional[str] = None
    documents: List[TransmittalDocItem]
    issue_now: bool = False


class TransmittalResponse(BaseModel):
    id: str
    transmittal_no: str
    subject: str
    created_at: datetime
    doc_count: int
    status: str
    void_reason: Optional[str] = None
    voided_by: Optional[str] = None
    voided_at: Optional[str] = None


class TransmittalDetailResponse(BaseModel):
    id: str
    transmittal_no: str
    project_code: str
    sender: str
    receiver: str
    subject: str
    created_at: datetime
    status: str
    void_reason: Optional[str] = None
    voided_by: Optional[str] = None
    voided_at: Optional[str] = None
    documents: List[TransmittalDocItem]


class EligibleDocumentResponse(BaseModel):
    doc_number: str
    doc_title: str
    project_code: str
    discipline_code: Optional[str] = None
    revision: str
    status: str


class TransmittalVoidIn(BaseModel):
    reason: str = Field(..., min_length=1)


def _generate_transmittal_id(db: Session, project: str, sender: str, receiver: str) -> str:
    """
    Format: {PROJECT}-T-{SENDER}-{RECEIVER}-{YYMM}{SERIAL}
    Example: T202-T-O-C-2402001
    """
    prefix = f"{project}-T-{sender}-{receiver}-{datetime.now().strftime('%y%m')}"
    last_t = (
        db.query(Transmittal)
        .filter(Transmittal.id.like(f"{prefix}%"))
        .order_by(Transmittal.id.desc())
        .first()
    )

    if last_t:
        try:
            last_serial = int(last_t.id[-3:])
            new_serial = last_serial + 1
        except Exception:
            new_serial = 1
    else:
        new_serial = 1

    return f"{prefix}{new_serial:03d}"


def _display_subject(transmittal: Transmittal) -> str:
    if transmittal.docs:
        first_title = transmittal.docs[0].document_title
        if first_title:
            return first_title
    return f"{transmittal.sender} -> {transmittal.receiver}"


def _normalize_code(value: str | None, fallback: str = "") -> str:
    return (value or fallback).strip().upper()


def _normalize_state(value: str | None) -> str:
    state = str(value or "").strip().lower()
    if state in {STATE_DRAFT, STATE_ISSUED, STATE_VOID}:
        return state
    # Legacy fallback for missing rows/columns.
    return STATE_ISSUED


def _get_transmittal_state_record(transmittal: Transmittal) -> Dict[str, Optional[str]]:
    status = _normalize_state(getattr(transmittal, "lifecycle_status", None))
    # Legacy fallback: transmittals created before lifecycle columns.
    if not getattr(transmittal, "lifecycle_status", None):
        status = STATE_ISSUED if transmittal.send_date else STATE_DRAFT
    return {
        "status": status,
        "void_reason": getattr(transmittal, "void_reason", None),
        "voided_by": getattr(transmittal, "voided_by", None),
        "voided_at": transmittal.voided_at.isoformat() if getattr(transmittal, "voided_at", None) else None,
    }


def _set_transmittal_state(
    transmittal: Transmittal,
    state: str,
    *,
    void_reason: Optional[str] = None,
    voided_by: Optional[str] = None,
    voided_at: Optional[datetime] = None,
) -> None:
    normalized_state = _normalize_state(state)
    transmittal.lifecycle_status = normalized_state
    if normalized_state == STATE_VOID:
        transmittal.void_reason = str(void_reason or "").strip() or None
        transmittal.voided_by = str(voided_by or "").strip() or None
        transmittal.voided_at = voided_at
    else:
        transmittal.void_reason = None
        transmittal.voided_by = None
        transmittal.voided_at = None


def _validate_payload_documents(
    db: Session,
    user: User,
    project_code: str,
    documents: List[TransmittalDocItem],
) -> dict[str, MdrDocument]:
    doc_numbers = [d.document_code.strip() for d in documents if d.document_code.strip()]
    if len(set(doc_numbers)) != len(doc_numbers):
        raise HTTPException(status_code=400, detail="Duplicate document_code in payload")

    docs_by_code: dict[str, MdrDocument] = {}
    if not doc_numbers:
        return docs_by_code

    found_docs = db.query(MdrDocument).filter(MdrDocument.doc_number.in_(doc_numbers)).all()
    docs_by_code = {d.doc_number: d for d in found_docs}

    missing = sorted(set(doc_numbers) - set(docs_by_code.keys()))
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Some documents were not found: {', '.join(missing[:5])}",
        )

    for doc in docs_by_code.values():
        if _normalize_code(doc.project_code) != project_code:
            raise HTTPException(
                status_code=400,
                detail=f"Document {doc.doc_number} does not belong to project {project_code}",
            )
        enforce_scope_access(
            db,
            user,
            project_code=doc.project_code,
            discipline_code=doc.discipline_code,
        )
    return docs_by_code


@router.get("/next-number")
def get_next_transmittal_number(
    project_code: str,
    sender: str = "O",
    receiver: str = "C",
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:create")),
):
    project = _normalize_code(project_code)
    if not project:
        raise HTTPException(status_code=400, detail="project_code is required")
    enforce_scope_access(db, user, project_code=project)
    number = _generate_transmittal_id(
        db,
        project=project,
        sender=_normalize_code(sender, "O"),
        receiver=_normalize_code(receiver, "C"),
    )
    return {"ok": True, "transmittal_no": number}


@router.get("/eligible-docs", response_model=List[EligibleDocumentResponse])
def get_eligible_documents(
    project_code: str,
    discipline_code: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:create")),
):
    project = _normalize_code(project_code)
    if not project:
        raise HTTPException(status_code=400, detail="project_code is required")
    enforce_scope_access(db, user, project_code=project, discipline_code=discipline_code)

    latest_subq = (
        db.query(
            DocumentRevision.document_id.label("document_id"),
            func.max(DocumentRevision.created_at).label("max_created_at"),
        )
        .group_by(DocumentRevision.document_id)
        .subquery()
    )
    Rev = aliased(DocumentRevision)

    query = (
        db.query(MdrDocument, Rev)
        .outerjoin(latest_subq, latest_subq.c.document_id == MdrDocument.id)
        .outerjoin(
            Rev,
            (Rev.document_id == MdrDocument.id) & (Rev.created_at == latest_subq.c.max_created_at),
        )
    )
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=MdrDocument.project_code,
        discipline_column=MdrDocument.discipline_code,
    )
    query = query.filter(MdrDocument.project_code == project)

    discipline = _normalize_code(discipline_code)
    if discipline:
        query = query.filter(MdrDocument.discipline_code == discipline)

    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                MdrDocument.doc_number.ilike(term),
                MdrDocument.doc_title_e.ilike(term),
                MdrDocument.doc_title_p.ilike(term),
                MdrDocument.subject.ilike(term),
            )
        )

    rows = (
        query.order_by(MdrDocument.created_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [
        {
            "doc_number": doc.doc_number,
            "doc_title": doc.doc_title_p or doc.doc_title_e or doc.subject or doc.doc_number,
            "project_code": doc.project_code,
            "discipline_code": doc.discipline_code,
            "revision": rev.revision if rev else "00",
            "status": rev.status if rev else "Registered",
        }
        for doc, rev in rows
    ]


@router.get("/", response_model=List[TransmittalResponse])
def get_transmittals(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:read")),
):
    query = db.query(Transmittal)
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=Transmittal.project_code,
    )
    items = query.order_by(Transmittal.created_at.desc()).offset(skip).limit(limit).all()
    output = []
    for t in items:
        state_record = _get_transmittal_state_record(t)
        output.append(
            {
                "id": t.id,
                "transmittal_no": t.id,
                "subject": _display_subject(t),
                "created_at": t.created_at,
                "doc_count": len(t.docs),
                "status": state_record["status"],
                "void_reason": state_record["void_reason"],
                "voided_by": state_record["voided_by"],
                "voided_at": state_record["voided_at"],
            }
        )
    return output


@router.post("/create")
def create_transmittal(
    payload: TransmittalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:create")),
):
    project_code = _normalize_code(payload.project_code)
    sender = _normalize_code(payload.sender, "O")
    receiver = _normalize_code(payload.receiver, "C")

    enforce_scope_access(db, user, project_code=project_code)
    direction = sender if sender in {"I", "O"} else "O"

    docs_by_code = _validate_payload_documents(db, user, project_code, payload.documents)

    transmittal_id = _generate_transmittal_id(db, project_code, sender, receiver)

    new_tr = Transmittal(
        id=transmittal_id,
        project_code=project_code,
        direction=direction,
        sender=sender,
        receiver=receiver,
        created_by_id=user.id,
        created_by_name=user.full_name or user.email,
        created_at=datetime.utcnow(),
    )
    db.add(new_tr)

    for doc_item in payload.documents:
        mdr_doc = docs_by_code.get(doc_item.document_code.strip())
        doc_title = mdr_doc.doc_title_e if mdr_doc else "Unknown Title"

        tr_doc = TransmittalDoc(
            transmittal_id=new_tr.id,
            document_code=doc_item.document_code,
            document_title=doc_title,
            revision=doc_item.revision,
            status=doc_item.status,
            electronic_copy=doc_item.electronic_copy,
            hard_copy=doc_item.hard_copy,
        )
        db.add(tr_doc)

    try:
        initial_state = STATE_ISSUED if payload.issue_now else STATE_DRAFT
        _set_transmittal_state(new_tr, initial_state)
        if initial_state == STATE_ISSUED and not new_tr.send_date:
            new_tr.send_date = datetime.utcnow().date().isoformat()
        db.commit()
        return {
            "ok": True,
            "transmittal_no": transmittal_id,
            "status": initial_state,
            "message": "Transmittal created successfully",
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/item/{transmittal_id}", response_model=TransmittalDetailResponse)
def get_transmittal_detail(
    transmittal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:read")),
):
    tr = db.query(Transmittal).filter(Transmittal.id == transmittal_id).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Transmittal not found")

    enforce_scope_access(db, user, project_code=tr.project_code)
    state_record = _get_transmittal_state_record(tr)
    return {
        "id": tr.id,
        "transmittal_no": tr.id,
        "project_code": tr.project_code,
        "sender": tr.sender,
        "receiver": tr.receiver,
        "subject": _display_subject(tr),
        "created_at": tr.created_at,
        "status": state_record["status"],
        "void_reason": state_record["void_reason"],
        "voided_by": state_record["voided_by"],
        "voided_at": state_record["voided_at"],
        "documents": [
            {
                "document_code": d.document_code,
                "revision": d.revision or "00",
                "status": d.status or "IFA",
                "electronic_copy": bool(d.electronic_copy),
                "hard_copy": bool(d.hard_copy),
            }
            for d in tr.docs
        ],
    }


@router.put("/item/{transmittal_id}")
def edit_transmittal(
    transmittal_id: str,
    payload: TransmittalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:update")),
):
    tr = db.query(Transmittal).filter(Transmittal.id == transmittal_id).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Transmittal not found")

    enforce_scope_access(db, user, project_code=tr.project_code)

    state = _get_transmittal_state_record(tr)["status"]
    if state not in EDITABLE_STATES:
        raise HTTPException(status_code=409, detail=f"Only draft transmittals are editable (state={state})")

    payload_project = _normalize_code(payload.project_code)
    if payload_project != _normalize_code(tr.project_code):
        raise HTTPException(status_code=400, detail="project_code cannot be changed in edit")

    sender = _normalize_code(payload.sender, "O")
    receiver = _normalize_code(payload.receiver, "C")
    docs_by_code = _validate_payload_documents(db, user, payload_project, payload.documents)

    tr.sender = sender
    tr.receiver = receiver
    tr.direction = sender if sender in {"I", "O"} else "O"

    db.query(TransmittalDoc).filter(TransmittalDoc.transmittal_id == tr.id).delete(synchronize_session=False)
    for doc_item in payload.documents:
        mdr_doc = docs_by_code.get(doc_item.document_code.strip())
        doc_title = mdr_doc.doc_title_e if mdr_doc else "Unknown Title"
        db.add(
            TransmittalDoc(
                transmittal_id=tr.id,
                document_code=doc_item.document_code,
                document_title=doc_title,
                revision=doc_item.revision,
                status=doc_item.status,
                electronic_copy=doc_item.electronic_copy,
                hard_copy=doc_item.hard_copy,
            )
        )

    db.commit()
    return {"ok": True, "id": tr.id, "status": state, "message": "Transmittal draft updated"}


@router.post("/item/{transmittal_id}/issue")
def issue_transmittal(
    transmittal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:issue")),
):
    tr = db.query(Transmittal).filter(Transmittal.id == transmittal_id).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Transmittal not found")

    enforce_scope_access(db, user, project_code=tr.project_code)

    state = _get_transmittal_state_record(tr)["status"]
    if state != STATE_DRAFT:
        raise HTTPException(status_code=409, detail=f"Only draft transmittals can be issued (state={state})")

    _set_transmittal_state(tr, STATE_ISSUED)
    tr.send_date = tr.send_date or datetime.utcnow().date().isoformat()
    db.commit()
    return {"ok": True, "id": tr.id, "status": STATE_ISSUED, "message": "Transmittal issued"}


@router.post("/item/{transmittal_id}/void")
def void_transmittal(
    transmittal_id: str,
    payload: TransmittalVoidIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:void")),
):
    tr = db.query(Transmittal).filter(Transmittal.id == transmittal_id).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Transmittal not found")

    enforce_scope_access(db, user, project_code=tr.project_code)

    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Void reason is required")

    state_record = _get_transmittal_state_record(tr)
    state = state_record["status"]
    if state == STATE_VOID:
        return {
            "ok": True,
            "id": tr.id,
            "status": STATE_VOID,
            "void_reason": state_record["void_reason"],
            "voided_by": state_record["voided_by"],
            "voided_at": state_record["voided_at"],
            "message": "Transmittal already void",
        }
    if state not in VOIDABLE_STATES:
        raise HTTPException(status_code=409, detail=f"Cannot void transmittal in state={state}")

    voided_by = (user.full_name or user.email or "").strip() or "Unknown User"
    voided_at = datetime.utcnow()
    _set_transmittal_state(
        tr,
        STATE_VOID,
        void_reason=reason,
        voided_by=voided_by,
        voided_at=voided_at,
    )
    db.commit()
    return {
        "ok": True,
        "id": tr.id,
        "status": STATE_VOID,
        "void_reason": reason,
        "voided_by": voided_by,
        "voided_at": voided_at,
        "message": "Transmittal voided",
    }


@router.get("/{transmittal_id}/download-cover")
def download_cover_sheet(
    transmittal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:read")),
):
    tr = db.query(Transmittal).filter(Transmittal.id == transmittal_id).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Transmittal not found")
    enforce_scope_access(db, user, project_code=tr.project_code)
    state_record = _get_transmittal_state_record(tr)
    state = state_record["status"]
    watermark_text = None
    if state == STATE_DRAFT:
        watermark_text = "DRAFT - NOT ISSUED"
    elif state == STATE_VOID:
        watermark_text = "VOID"

    pdf_docs = [
        SimpleNamespace(
            document_code=d.document_code,
            revision=d.revision,
            status=d.status,
            document_title=d.document_title,
            electronic_copy=d.electronic_copy,
            hard_copy=d.hard_copy,
        )
        for d in tr.docs
    ]

    pdf_payload = SimpleNamespace(
        transmittal_no=tr.id,
        subject=_display_subject(tr),
        created_at=tr.created_at or datetime.utcnow(),
        sender=tr.sender,
        receiver=tr.receiver,
        notes=None,
        documents=pdf_docs,
    )

    pdf_buffer = generate_transmittal_pdf(
        pdf_payload,
        project_name=f"Project {tr.project_code}",
        watermark_text=watermark_text,
    )
    filename = f"Transmittal_{tr.id}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/stats/summary")
def get_transmittal_stats(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:read")),
):
    scoped_query = apply_scope_query_filters(
        db.query(Transmittal),
        db,
        user,
        project_column=Transmittal.project_code,
    )
    total = scoped_query.count()

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)

    this_month = scoped_query.filter(
        Transmittal.created_at >= month_start,
        Transmittal.created_at < next_month,
    ).count()

    last_created = scoped_query.order_by(Transmittal.created_at.desc()).first()

    return {
        "total_transmittals": total,
        "this_month": this_month,
        "last_created": last_created.id if last_created else "-",
    }
