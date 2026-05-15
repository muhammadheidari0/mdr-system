from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query
from fastapi.responses import FileResponse 

from pydantic import BaseModel
from sqlalchemy.orm import Session, aliased
from sqlalchemy import or_, func

# ✅ ایمپورت‌های امنیتی جدید
from app.api.dependencies import (
    get_db,
    User,
    apply_scope_query_filters,
    enforce_scope_access,
    has_permission_for_user,
    require_permission,
)
from app.core.config import settings
from app.db.models import (
    MdrDocument, 
    DocumentRevision, 
    Project, 
    Phase, 
    MdrCategory
)

# Use service layer
from app.services import (
    archive_service,
    docnum_service,
    mdr_service,
    import_service
)

router = APIRouter(prefix="/mdr", tags=["MDR"])

MAX_IMPORT_FILE_SIZE_MB = 15
MAX_IMPORT_FILE_SIZE_BYTES = MAX_IMPORT_FILE_SIZE_MB * 1024 * 1024
MAX_BULK_ROWS = 10000
MAX_BULK_TEXT_BYTES = 10 * 1024 * 1024

# ----------------------------------------------------------------
# 1. Request Models & Enums
# ----------------------------------------------------------------
class DocumentStatus(str, Enum):
    DRAFT = "Draft"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    IFA = "IFA"
    IFC = "IFC"
    ASB = "ASB"
    CREATED = "Created"

class DocumentRequest(BaseModel):
    project_code: str
    mdr_code: Optional[str] = None      # 'E', 'P', 'C'
    sheetName: Optional[str] = None     # Fallback
    phase: str
    discipline: str
    packageE: str
    block: str
    location: str
    subjectE: str
    subjectP: str
    serialNumber: Optional[int] = None  # Manual

class BulkImportRequest(BaseModel):
    text_data: str


class BulkRegisterRow(BaseModel):
    project: Optional[str] = None
    mdr: Optional[str] = None
    phase: Optional[str] = None
    disc: Optional[str] = None
    pkg: Optional[str] = None
    block: Optional[str] = None
    level: Optional[str] = None
    subject: Optional[str] = None
    titleP: Optional[str] = None
    titleE: Optional[str] = None
    code: Optional[str] = None
    providedCode: Optional[bool] = None
    revision: Optional[str] = None
    status: Optional[str] = None

# ----------------------------------------------------------------
# 2. Local Helpers
# ----------------------------------------------------------------
def _get_project(db: Session, project_code: str) -> Project:
    proj = db.query(Project).filter(Project.code == project_code).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    return proj

def _get_mdr_code(req: DocumentRequest, db: Session) -> str:
    def ensure_active(code_value: str) -> str:
        code = code_value.strip().upper()
        exists = (
            db.query(MdrCategory)
            .filter(MdrCategory.code == code, MdrCategory.is_active.is_(True))
            .first()
        )
        if not exists:
            raise HTTPException(status_code=400, detail=f"Invalid or inactive MDR Code: {code}")
        return code

    if req.mdr_code:
        return ensure_active(req.mdr_code)
    
    s = (req.sheetName or "").lower()
    if "engineering" in s: return ensure_active("E")
    if "procurement" in s: return ensure_active("P")
    if "construction" in s: return ensure_active("C")
    return ensure_active("E") 

def _resolve_phase(db: Session, phase_value: str) -> tuple[str, str]:
    v = (phase_value or "").strip()
    if not v: return "X", "Unknown"
    
    row = db.query(Phase).filter((Phase.ph_code == v) | (Phase.name_e == v)).first()
    if row: 
        return row.ph_code, (row.name_e or row.ph_code)
    
    return (v, v) if len(v) <= 5 else ("X", v)


async def _read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File is too large. Maximum allowed size is {MAX_IMPORT_FILE_SIZE_MB} MB. "
                    "Please split the file and retry."
                ),
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_bulk_text_limits(text_data: str) -> None:
    text_size = len(text_data.encode("utf-8"))
    if text_size > MAX_BULK_TEXT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "Bulk payload is too large. Split the file into smaller batches and retry."
            ),
        )

    row_count = len([line for line in text_data.splitlines() if line.strip()])
    if row_count > MAX_BULK_ROWS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Too many rows ({row_count}). Maximum allowed rows per submit is {MAX_BULK_ROWS}."
            ),
        )


def _rows_to_bulk_text(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows:
        provided = bool(row.get("providedCode"))
        raw_code = str(row.get("code") or "").strip()
        parts = [
            str(row.get("project") or "T202").strip() or "T202",
            str(row.get("mdr") or "E").strip() or "E",
            str(row.get("phase") or "X").strip() or "X",
            str(row.get("disc") or "GN").strip() or "GN",
            str(row.get("pkg") or "00").strip() or "00",
            str(row.get("block") or "G").strip() or "G",
            str(row.get("level") or "GEN").strip() or "GEN",
            str(row.get("subject") or "").strip(),
            str(row.get("titleP") or "").strip(),
            str(row.get("titleE") or "").strip(),
            raw_code if provided and raw_code else "",
        ]
        lines.append("\t".join(parts))
    return ("\n".join(lines) + "\n") if lines else ""


def _calc_next_revision_code(current_rev: str | None) -> str:
    rev = str(current_rev or "").strip()
    if not rev:
        return "00"
    if rev.isdigit():
        try:
            return f"{int(rev) + 1:02d}"
        except Exception:
            return "00"
    if len(rev) == 1 and rev.isalpha():
        up = rev.upper()
        if up < "Z":
            return chr(ord(up) + 1)
        return up
    return rev


def _next_revision_for_document(db: Session, document_id: int) -> str:
    last_rev = (
        db.query(DocumentRevision)
        .filter(DocumentRevision.document_id == document_id)
        .order_by(DocumentRevision.created_at.desc())
        .first()
    )
    if not last_rev:
        return "00"
    return _calc_next_revision_code(last_rev.revision)

# ----------------------------------------------------------------
# 3. Endpoints (Secured 🔒)
# ----------------------------------------------------------------

# این صفحه HTML است و معمولاً داخل پنل لود می‌شود، پس نیازی به توکن در هدر ندارد
@router.get("/bulk-register-page", response_class=FileResponse)
def get_bulk_register_page():
    html_path = settings.BASE_DIR / "templates" / "mdr" / "bulk_register.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="HTML file not found")
    return FileResponse(
        html_path,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

# 🔒 فقط ادیتورها می‌توانند سند تکی ثبت کنند
@router.post("/submit")
def submit_document(
    req: DocumentRequest, 
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:create"))
):
    enforce_scope_access(
        db,
        user,
        project_code=req.project_code,
        discipline_code=req.discipline,
    )
    proj = _get_project(db, req.project_code)
    mdr_code = _get_mdr_code(req, db)
    phase_code, _ = _resolve_phase(db, req.phase)
    subject_key = str(req.subjectP or "").strip()
    subject_storage = subject_key or str(req.subjectE or "").strip()

    existing_doc = None
    if subject_key:
        existing_doc = mdr_service.find_document_by_metadata_key(
            db,
            project_code=proj.code,
            mdr_code=mdr_code,
            phase_code=phase_code,
            discipline_code=req.discipline,
            package_code=req.packageE,
            block=req.block,
            level_code=req.location,
            subject=subject_key,
        )
    if existing_doc:
        raise HTTPException(
            status_code=409,
            detail=f"این مدرک قبلاً ثبت شده است: {existing_doc.doc_number}",
        )

    doc_num, serial_str = docnum_service.generate_next_doc_number(
        db,
        proj.code,
        mdr_code,
        phase_code,
        req.discipline,
        req.packageE,
        req.block,
        req.location,
        subject_key,
        req.serialNumber,
    )

    try:
        new_doc = mdr_service.create_mdr_document(
            db, doc_num, proj.code, mdr_code, phase_code, req.discipline, 
            req.packageE, req.block, req.location, req.subjectE, req.subjectP, subject_storage
        )
        db.commit()
        return {"ok": True, "docNumber": doc_num, "id": new_doc.id, "message": "Document created"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 🔒 فقط ادیتورها می‌توانند فایل آپلود و پردازش کنند
@router.post("/parse-import-source")
async def parse_import_source(
    file: UploadFile = File(None),
    url: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:create"))
):
    """آپلود و پردازش اولیه فایل اکسل برای پیش‌نمایش"""
    if not file and not (url and url.strip()):
        raise HTTPException(
            status_code=400,
            detail="Excel file or Google Sheet URL is required.",
        )

    content = None
    if file:
        filename = (file.filename or "").lower()
        if filename and not filename.endswith((".xlsx", ".xls", ".csv")):
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Please upload .xlsx, .xls, or .csv.",
            )
        content = await _read_upload_limited(file, MAX_IMPORT_FILE_SIZE_BYTES)
    elif url and not url.strip().startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL format. URL must start with http:// or https://",
        )
    
    data = import_service.parse_excel_or_link(file_content=content, url=url)
    if not data:
        raise HTTPException(
            status_code=400,
            detail="No valid rows were detected in the source. Check your template and retry.",
        )
    if len(data) > MAX_BULK_ROWS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Too many rows ({len(data)}). Maximum supported rows per upload is {MAX_BULK_ROWS}. "
                "Please split the file into smaller batches."
            ),
        )
    return {"ok": True, "rows": data, "count": len(data)}

# 🔒 ثبت نهایی گروهی
@router.post("/bulk-register")
def bulk_register_docs(
    payload: BulkImportRequest, 
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:create"))
):
    raw_text_data = payload.text_data or ""
    if not raw_text_data.strip():
        raise HTTPException(
            status_code=400,
            detail="Bulk payload is empty. Add at least one row before submit.",
        )

    # Keep original tabs/newlines intact; they are required for column mapping.
    text_data = raw_text_data
    _validate_bulk_text_limits(text_data)

    result = import_service.process_bulk_text(db, text_data)
    return result


@router.post("/bulk-register-with-files")
async def bulk_register_docs_with_files(
    rows_json: str = Form(...),
    files_manifest: str = Form("[]"),
    revision: str = Form("00"),
    status: str = Form("Registered"),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:create")),
):
    try:
        raw_rows = json.loads(rows_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid rows payload JSON.") from exc

    if not isinstance(raw_rows, list) or not raw_rows:
        raise HTTPException(status_code=400, detail="Rows payload is empty.")
    if len(raw_rows) > MAX_BULK_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Too many rows ({len(raw_rows)}). Maximum allowed rows is {MAX_BULK_ROWS}.",
        )

    rows: list[dict[str, Any]] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Invalid row item in payload.")
        validated = BulkRegisterRow(**item)
        rows.append(validated.model_dump() if hasattr(validated, "model_dump") else validated.dict())

    text_data = _rows_to_bulk_text(rows)
    _validate_bulk_text_limits(text_data)

    result = import_service.process_bulk_text(db, text_data)
    if not result.get("ok"):
        return result

    try:
        manifest = json.loads(files_manifest or "[]")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid files manifest JSON.") from exc

    if not manifest:
        result["uploads"] = {
            "rows_with_files": 0,
            "uploaded": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }
        return result

    if not has_permission_for_user(db, user, "archive:update"):
        raise HTTPException(
            status_code=403,
            detail="Missing permission: archive:update",
        )

    details = result.get("stats", {}).get("details", [])
    success_doc_by_row_index: dict[int, str] = {}
    for idx, item in enumerate(details):
        row_status = str(item.get("status") or "").lower()
        if row_status in {"success", "skipped"}:
            doc_number = str(item.get("doc_number") or "").strip()
            if doc_number:
                success_doc_by_row_index[idx] = doc_number

    grouped: dict[int, dict[str, UploadFile]] = defaultdict(dict)
    for entry in manifest:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "").strip().lower()
        if kind not in {"pdf", "native"}:
            continue
        row_index = int(entry.get("row_index", -1))
        file_index = int(entry.get("file_index", -1))
        if row_index < 0 or file_index < 0:
            continue
        if file_index >= len(files):
            continue
        grouped[row_index][kind] = files[file_index]

    upload_details: list[dict[str, Any]] = []
    upload_success = 0
    upload_failed = 0
    upload_skipped = 0

    # Kept for backward compatibility in request shape; revision is auto-generated per archive rules.
    _ = str(revision or "00").strip() or "00"
    safe_status = str(status or "Registered").strip() or "Registered"

    for row_index, mapping in sorted(grouped.items(), key=lambda x: x[0]):
        doc_number = success_doc_by_row_index.get(row_index)
        if not doc_number:
            upload_skipped += 1
            upload_details.append(
                {
                    "row_index": row_index,
                    "status": "Skipped",
                    "message": "Document row was not created successfully in bulk step.",
                }
            )
            continue

        document = db.query(MdrDocument).filter(MdrDocument.doc_number == doc_number).first()
        if not document:
            upload_failed += 1
            upload_details.append(
                {
                    "row_index": row_index,
                    "doc_number": doc_number,
                    "status": "Failed",
                    "message": "Document not found after bulk insert.",
                }
            )
            continue

        enforce_scope_access(
            db,
            user,
            project_code=document.project_code,
            discipline_code=document.discipline_code,
        )

        pdf_file = mapping.get("pdf")
        native_file = mapping.get("native")
        row_payload = rows[row_index] if 0 <= row_index < len(rows) else {}
        row_status = str(row_payload.get("status") or safe_status).strip() or safe_status
        row_revision = _next_revision_for_document(db, document.id)
        try:
            if pdf_file and native_file:
                archive_service.save_dual_upload_files(
                    db=db,
                    pdf_file=pdf_file,
                    native_file=native_file,
                    document_id=document.id,
                    revision_code=row_revision,
                    status_code=row_status,
                    is_admin=user.role == "admin",
                )
            elif pdf_file:
                archive_service.save_upload_file(
                    db=db,
                    file=pdf_file,
                    document_id=document.id,
                    revision_code=row_revision,
                    status_code=row_status,
                    file_kind="pdf",
                    is_primary=True,
                    is_admin=user.role == "admin",
                )
            elif native_file:
                archive_service.save_upload_file(
                    db=db,
                    file=native_file,
                    document_id=document.id,
                    revision_code=row_revision,
                    status_code=row_status,
                    file_kind="native",
                    is_primary=False,
                    is_admin=user.role == "admin",
                )
            else:
                upload_skipped += 1
                upload_details.append(
                    {
                        "row_index": row_index,
                        "doc_number": doc_number,
                        "revision": row_revision,
                        "status_code": row_status,
                        "status": "Skipped",
                        "message": "No upload file was mapped for this row.",
                    }
                )
                continue

            upload_success += 1
            upload_details.append(
                {
                    "row_index": row_index,
                    "doc_number": doc_number,
                    "revision": row_revision,
                    "status_code": row_status,
                    "status": "Success",
                    "message": "Archive file(s) uploaded.",
                }
            )
        except Exception as exc:
            upload_failed += 1
            upload_details.append(
                {
                    "row_index": row_index,
                    "doc_number": doc_number,
                    "revision": row_revision,
                    "status_code": row_status,
                    "status": "Failed",
                    "message": str(exc),
                }
            )

    result["uploads"] = {
        "rows_with_files": len(grouped),
        "uploaded": upload_success,
        "failed": upload_failed,
        "skipped": upload_skipped,
        "details": upload_details,
    }
    return result


@router.get("/subject-suggestions")
def subject_suggestions(
    project_code: str = Query(...),
    mdr_code: str = Query(...),
    phase: str = Query(...),
    pkg: str = Query(...),
    discipline_code: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:read")),
):
    prj = str(project_code or "").strip().upper()
    mdr = str(mdr_code or "").strip().upper()
    ph = str(phase or "").strip().upper()
    package = str(pkg or "").strip().upper()
    disc = str(discipline_code or "").strip().upper() or None

    if not prj or not mdr or not ph or not package:
        return {"ok": True, "items": []}

    enforce_scope_access(
        db,
        user,
        project_code=prj,
        discipline_code=disc,
    )

    pkg_candidates: list[str] = []
    if package:
        pkg_candidates.append(package)
        if disc and package.startswith(disc) and len(package) > len(disc):
            stripped = package[len(disc) :].strip()
            if stripped:
                pkg_candidates.append(stripped)
        if disc and not package.startswith(disc):
            pkg_candidates.append(f"{disc}{package}")
    pkg_candidates = [p for i, p in enumerate(pkg_candidates) if p and p not in pkg_candidates[:i]]

    query = (
        db.query(MdrDocument.subject)
        .filter(MdrDocument.project_code == prj)
        .filter(MdrDocument.mdr_code == mdr)
        .filter(MdrDocument.phase_code == ph)
        .filter(MdrDocument.subject.isnot(None))
        .filter(MdrDocument.subject != "")
    )
    if disc:
        query = query.filter(MdrDocument.discipline_code == disc)
    if pkg_candidates:
        query = query.filter(MdrDocument.package_code.in_(pkg_candidates))
    term = str(q or "").strip()
    if term:
        query = query.filter(MdrDocument.subject.ilike(f"%{term}%"))

    rows = query.order_by(MdrDocument.created_at.desc()).limit(max(limit * 10, 50)).all()

    items: list[str] = []
    seen = set()
    for (subject,) in rows:
        value = str(subject or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(value)
        if len(items) >= limit:
            break

    return {"ok": True, "items": items}

# 🔒 همه کاربران مجاز (Viewer به بالا) می‌توانند جستجو کنند
@router.get("/search")
def search_documents(
    project_code: Optional[str] = None, 
    mdr_code: Optional[str] = None,
    discipline_code: Optional[str] = None,
    doc: Optional[str] = None, 
    subject: Optional[str] = None,
    status: Optional[str] = None, 
    revision: Optional[str] = None,
    page: int = 1, 
    size: int = 20, 
    sort_by: str = "created_at", 
    sort_dir: str = "desc",
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:read"))
): 
    latest_subq = (
        db.query(DocumentRevision.document_id.label("document_id"), func.max(DocumentRevision.created_at).label("max_created_at"))
        .group_by(DocumentRevision.document_id).subquery()
    )
    Rev = aliased(DocumentRevision)
    q = db.query(MdrDocument, Rev).outerjoin(latest_subq, latest_subq.c.document_id == MdrDocument.id).outerjoin(Rev, (Rev.document_id == MdrDocument.id) & (Rev.created_at == latest_subq.c.max_created_at))
    q = apply_scope_query_filters(
        q,
        db,
        user,
        project_column=MdrDocument.project_code,
        discipline_column=MdrDocument.discipline_code,
    )
    
    if project_code: q = q.filter(MdrDocument.project_code == project_code)
    if mdr_code: q = q.filter(MdrDocument.mdr_code == mdr_code)
    if project_code:
        enforce_scope_access(db, user, project_code=project_code)
    if discipline_code:
        enforce_scope_access(db, user, discipline_code=discipline_code)
        q = q.filter(MdrDocument.discipline_code == discipline_code)
    if revision: q = q.filter(Rev.revision == revision)
    if status: q = q.filter(Rev.status.ilike(f"%{status}%"))
    if doc: q = q.filter(MdrDocument.doc_number.ilike(f"%{doc.strip().replace(' ', '%')}%"))
    if subject: 
        s = f"%{subject}%"
        q = q.filter(or_(MdrDocument.doc_title_e.ilike(s), MdrDocument.doc_title_p.ilike(s), MdrDocument.subject.ilike(s)))

    sort_map = {"doc_number": MdrDocument.doc_number, "created_at": MdrDocument.created_at}
    sort_col = sort_map.get(sort_by, MdrDocument.created_at)
    q = q.order_by(sort_col.asc() if sort_dir == "asc" else sort_col.desc())

    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()

    return {
        "ok": True, "total": total, "page": page, "size": size,
        "items": [{
            "id": d.id, "doc_number": d.doc_number, "project_code": d.project_code,
            "status": (r.status if r else "Registered"), "revision": (r.revision if r else "-"),
            "doc_title_e": d.doc_title_e or d.subject, "created_at": d.created_at.isoformat() if d.created_at else None
        } for (d, r) in rows]
    }
