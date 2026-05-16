from datetime import date, datetime
from html import escape as html_escape
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
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
    ArchiveFile,
    ArchiveFilePublicShare,
    Correspondence,
    CorrespondenceExternalRelation,
    DocumentRevision,
    MdrDocument,
    Transmittal,
    TransmittalDoc,
)
from app.services.document_activity_service import log_document_activity
from app.services.pdf_service import generate_transmittal_pdf
from app.services.transmittal_options import (
    transmittal_options_payload,
    transmittal_party_label,
)

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
    file_kind: str = "pdf"
    electronic_copy: bool = True
    hard_copy: bool = False
    document_title: Optional[str] = None
    file_label: Optional[str] = None
    file_options: List[Dict[str, object]] = Field(default_factory=list)


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
    sender_label: Optional[str] = None
    receiver_label: Optional[str] = None
    void_reason: Optional[str] = None
    voided_by: Optional[str] = None
    voided_at: Optional[str] = None


class TransmittalDetailResponse(BaseModel):
    id: str
    transmittal_no: str
    project_code: str
    sender: str
    receiver: str
    sender_label: Optional[str] = None
    receiver_label: Optional[str] = None
    subject: str
    created_at: datetime
    status: str
    void_reason: Optional[str] = None
    voided_by: Optional[str] = None
    voided_at: Optional[str] = None
    documents: List[TransmittalDocItem]
    correspondence_relations: List[Dict[str, object]] = Field(default_factory=list)


class EligibleDocumentResponse(BaseModel):
    doc_number: str
    doc_title: str
    project_code: str
    discipline_code: Optional[str] = None
    revision: str
    status: str
    default_file_kind: str = "pdf"
    file_options: List[Dict[str, object]] = Field(default_factory=list)


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


def _transmittal_party_labels(db: Session, transmittal: Transmittal) -> Dict[str, str]:
    return {
        "sender_label": transmittal_party_label(db, "direction_options", transmittal.sender),
        "receiver_label": transmittal_party_label(db, "recipient_options", transmittal.receiver),
    }


def _display_subject_with_labels(db: Session, transmittal: Transmittal) -> str:
    if transmittal.docs:
        first_title = transmittal.docs[0].document_title
        if first_title:
            return first_title
    labels = _transmittal_party_labels(db, transmittal)
    return f"{labels['sender_label']} -> {labels['receiver_label']}"


def _status_label(value: Any) -> str:
    key = str(value or "").strip().lower()
    return {
        STATE_DRAFT: "پیش‌نویس",
        STATE_ISSUED: "صادر شده",
        STATE_VOID: "باطل",
    }.get(key, str(value or "-").strip() or "-")


def _gregorian_to_jalali(g_year: int, g_month: int, g_day: int) -> tuple[int, int, int]:
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    gy = g_year - 1600
    gm = g_month - 1
    gd = g_day - 1
    g_day_no = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400
    for idx in range(gm):
        g_day_no += g_days_in_month[idx]
    if gm > 1 and ((gy + 1600) % 4 == 0 and ((gy + 1600) % 100 != 0 or (gy + 1600) % 400 == 0)):
        g_day_no += 1
    g_day_no += gd
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    jm = 0
    while jm < 11 and j_day_no >= j_days_in_month[jm]:
        j_day_no -= j_days_in_month[jm]
        jm += 1
    return jy, jm + 1, j_day_no + 1


def _format_jalali_date(value: Any) -> str:
    if value is None:
        return "-"
    parsed: date | datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return "-"
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return text.split("T", 1)[0] or "-"
    jy, jm, jd = _gregorian_to_jalali(parsed.year, parsed.month, parsed.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def _safe_text(value: Any, fallback: str = "-") -> str:
    text = str(value if value is not None else "").strip()
    return text or fallback


def _uniq_join(values: List[Any]) -> str:
    seen: list[str] = []
    for value in values:
        text = _safe_text(value, "")
        if text and text not in seen:
            seen.append(text)
    return "، ".join(seen) if seen else "-"


def _normalize_transmittal_file_kind(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"native", "dwg", "dxf", "editable", "cad"}:
        return "native"
    return "pdf"


def _transmittal_file_label(value: Any) -> str:
    return "DWG" if _normalize_transmittal_file_kind(value) == "native" else "PDF"


def _archive_file_kind(row: ArchiveFile) -> str:
    raw = str(row.file_kind or "").strip().lower()
    name = str(row.original_name or "").strip().lower()
    mime = str(row.mime_type or row.detected_mime or "").strip().lower()
    if raw in {"native", "dwg", "dxf", "editable", "cad"}:
        return "native"
    if name.endswith((".dwg", ".dxf")):
        return "native"
    if raw == "pdf" or mime in {"application/pdf", "application/x-pdf"} or name.endswith(".pdf"):
        return "pdf"
    return "pdf"


def _latest_revision(document: MdrDocument) -> Optional[DocumentRevision]:
    revisions = list(document.revisions or [])
    if not revisions:
        return None
    return sorted(
        revisions,
        key=lambda row: (row.created_at or datetime.min, int(row.id or 0)),
        reverse=True,
    )[0]


def _document_revision_by_code(document: MdrDocument, revision_code: Any) -> Optional[DocumentRevision]:
    revision = str(revision_code or "").strip()
    if revision:
        for row in document.revisions or []:
            if str(row.revision or "").strip() == revision:
                return row
    return _latest_revision(document)


def _revision_file_options(revision: Optional[DocumentRevision]) -> List[Dict[str, object]]:
    if revision is None:
        return []

    options: dict[str, Dict[str, object]] = {}
    for row in revision.archive_files or []:
        if getattr(row, "deleted_at", None) is not None:
            continue
        kind = _archive_file_kind(row)
        if kind not in options:
            options[kind] = {
                "value": kind,
                "label": _transmittal_file_label(kind),
                "file_id": int(row.id or 0),
                "file_name": row.original_name,
            }

    if "pdf" not in options:
        legacy_name = str(revision.file_name or revision.file_path or "").strip()
        if legacy_name.lower().endswith(".pdf"):
            options["pdf"] = {
                "value": "pdf",
                "label": _transmittal_file_label("pdf"),
                "file_id": None,
                "file_name": revision.file_name,
            }

    ordered: List[Dict[str, object]] = []
    for kind in ("pdf", "native"):
        if kind in options:
            ordered.append(options[kind])
    return ordered


def _default_file_kind(options: List[Dict[str, object]], fallback: Any = "pdf") -> str:
    values = {str(option.get("value") or "").strip().lower() for option in options}
    if "pdf" in values:
        return "pdf"
    if "native" in values:
        return "native"
    return _normalize_transmittal_file_kind(fallback)


def _copy_format_label(doc: TransmittalDoc) -> str:
    electronic = bool(doc.electronic_copy)
    hard = bool(doc.hard_copy)
    file_label = _transmittal_file_label(getattr(doc, "file_kind", "pdf"))
    if electronic and hard:
        return f"{file_label} / کاغذی"
    if electronic:
        return file_label
    if hard:
        return "کاغذی"
    return "-"


def _purpose_flags(docs: List[TransmittalDoc]) -> Dict[str, bool]:
    statuses = {str(doc.status or "").strip().upper() for doc in docs}
    return {
        "approval": any(item in statuses for item in {"IFA", "AFC", "APPROVAL"}),
        "review": any(item in statuses for item in {"IFR", "REVIEW"}),
        "info": any(item in statuses for item in {"IFI", "INFO", "INFORMATION"}),
        "execution": any(item in statuses for item in {"IFC", "AFC", "EXECUTION"}),
        "archive": False,
    }


def _checkbox_html(checked: bool) -> str:
    return '<span class="check is-checked"></span>' if checked else '<span class="check"></span>'


def _active_pdf_public_share_url(
    db: Session,
    document: Optional[MdrDocument],
    transmittal_doc: TransmittalDoc,
) -> Optional[str]:
    if document is None:
        return None
    if not bool(transmittal_doc.electronic_copy):
        return None
    if _normalize_transmittal_file_kind(getattr(transmittal_doc, "file_kind", "pdf")) != "pdf":
        return None

    now = datetime.utcnow()
    pdf_file_filter = or_(
        func.lower(func.coalesce(ArchiveFile.file_kind, "")) == "pdf",
        func.lower(func.coalesce(ArchiveFile.mime_type, "")).in_(["application/pdf", "application/x-pdf"]),
        func.lower(func.coalesce(ArchiveFile.detected_mime, "")).in_(["application/pdf", "application/x-pdf"]),
        ArchiveFile.original_name.ilike("%.pdf"),
    )
    base_query = (
        db.query(ArchiveFilePublicShare)
        .join(ArchiveFile, ArchiveFilePublicShare.file_id == ArchiveFile.id)
        .join(DocumentRevision, ArchiveFile.revision_id == DocumentRevision.id)
        .filter(
            DocumentRevision.document_id == document.id,
            ArchiveFile.deleted_at.is_(None),
            ArchiveFilePublicShare.provider == "nextcloud",
            ArchiveFilePublicShare.revoked_at.is_(None),
            or_(ArchiveFilePublicShare.expires_at.is_(None), ArchiveFilePublicShare.expires_at > now),
            pdf_file_filter,
        )
    )

    revision = _safe_text(transmittal_doc.revision, "").strip()
    if revision:
        exact_share = (
            base_query.filter(or_(DocumentRevision.revision == revision, ArchiveFile.revision == revision))
            .order_by(
                ArchiveFilePublicShare.created_at.desc(),
                ArchiveFile.uploaded_at.desc(),
                ArchiveFilePublicShare.id.desc(),
            )
            .first()
        )
        if exact_share is not None:
            return exact_share.share_url

    latest_share = (
        base_query.order_by(
            DocumentRevision.created_at.desc(),
            ArchiveFile.uploaded_at.desc(),
            ArchiveFilePublicShare.created_at.desc(),
            ArchiveFilePublicShare.id.desc(),
        )
        .first()
    )
    return latest_share.share_url if latest_share is not None else None


def _download_link_html(url: Optional[str]) -> str:
    if not url:
        return "-"
    escaped_url = html_escape(url, quote=True)
    return f'<a class="download-link" href="{escaped_url}" target="_blank" rel="noopener noreferrer">دانلود</a>'


def _build_transmittal_pdf_payload(db: Session, tr: Transmittal) -> SimpleNamespace:
    doc_codes = [str(doc.document_code or "").strip() for doc in tr.docs if str(doc.document_code or "").strip()]
    mdr_rows: dict[str, MdrDocument] = {}
    if doc_codes:
        mdr_rows = {
            row.doc_number: row
            for row in db.query(MdrDocument).filter(MdrDocument.doc_number.in_(doc_codes)).all()
        }
    pdf_docs = [
        SimpleNamespace(
            document_code=d.document_code,
            revision=d.revision,
            status=d.status,
            document_title=d.document_title,
            file_kind=_normalize_transmittal_file_kind(getattr(d, "file_kind", "pdf")),
            file_label=_transmittal_file_label(getattr(d, "file_kind", "pdf")),
            electronic_copy=d.electronic_copy,
            hard_copy=d.hard_copy,
            public_share_url=_active_pdf_public_share_url(db, mdr_rows.get(str(d.document_code or "").strip()), d),
        )
        for d in tr.docs
    ]
    return SimpleNamespace(
        transmittal_no=tr.id,
        subject=_display_subject_with_labels(db, tr),
        created_at=tr.created_at or datetime.utcnow(),
        sender=transmittal_party_label(db, "direction_options", tr.sender),
        receiver=transmittal_party_label(db, "recipient_options", tr.receiver),
        notes=None,
        documents=pdf_docs,
    )


def _render_transmittal_print_html(db: Session, tr: Transmittal) -> str:
    state_record = _get_transmittal_state_record(tr)
    sender_label = transmittal_party_label(db, "direction_options", tr.sender)
    receiver_label = transmittal_party_label(db, "recipient_options", tr.receiver)
    project = tr.project
    project_name = _safe_text(getattr(project, "name_p", None) or getattr(project, "name_e", None), f"Project {tr.project_code}")
    project_code = _safe_text(tr.project_code)
    doc_codes = [str(doc.document_code or "").strip() for doc in tr.docs if str(doc.document_code or "").strip()]
    mdr_rows: dict[str, MdrDocument] = {}
    if doc_codes:
        mdr_rows = {
            row.doc_number: row
            for row in db.query(MdrDocument).filter(MdrDocument.doc_number.in_(doc_codes)).all()
        }
    disciplines = _uniq_join([getattr(mdr_rows.get(code), "discipline_code", None) for code in doc_codes])
    packages = _uniq_join([getattr(mdr_rows.get(code), "package_code", None) for code in doc_codes])
    purposes = _purpose_flags(tr.docs)
    rows: list[str] = []
    for idx, doc in enumerate(tr.docs, 1):
        public_share_url = _active_pdf_public_share_url(db, mdr_rows.get(str(doc.document_code or "").strip()), doc)
        receive_note = "لینک عمومی Nextcloud" if public_share_url else (
            "نسخه کاغذی" if doc.hard_copy else (
                f"فایل {_transmittal_file_label(getattr(doc, 'file_kind', 'pdf'))}"
                if doc.electronic_copy
                else "-"
            )
        )
        rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td class=\"doc-no\">{html_escape(_safe_text(doc.document_code))}</td>"
            f"<td class=\"doc-title\">{html_escape(_safe_text(doc.document_title))}</td>"
            f"<td>{html_escape(_safe_text(doc.revision, '00'))}</td>"
            f"<td>{html_escape(_safe_text(doc.status, 'IFA'))}</td>"
            f"<td>1</td>"
            f"<td>{html_escape(_copy_format_label(doc))}</td>"
            f"<td>{_download_link_html(public_share_url)}</td>"
            f"<td>{html_escape(receive_note)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="9" class="empty-row">مدرکی در این ترنسمیتال ثبت نشده است.</td></tr>')

    html = f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>برگه ارسال مدارک - {html_escape(_safe_text(tr.id))}</title>
  <style>
    @page {{ size: A4; margin: 0; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #eef2f7;
      color: #111827;
      font-family: Tahoma, Arial, sans-serif;
      direction: rtl;
      font-size: 12px;
      line-height: 1.65;
    }}
    .sheet {{
      width: 210mm;
      min-height: 297mm;
      margin: 18px auto;
      padding: 0;
      background: #fff;
      box-shadow: 0 14px 34px rgba(15,23,42,.18);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}
    .print-header {{
      flex: 0 0 auto;
    }}
    .print-content {{
      flex: 1 1 auto;
      padding: 4mm 8mm 0;
    }}
    .print-footer {{
      flex: 0 0 auto;
      margin-top: auto;
      padding: 0 8mm;
    }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    td, th {{ border: 1px solid #1f2937; padding: 5px 6px; vertical-align: middle; }}
    th {{ background: #d9d9d9; font-weight: 800; text-align: center; }}
    .no-border td {{ border: 0; }}
    .header td {{ height: 28px; border-top: 0; }}
    .header > tbody > tr > td:first-child {{ border-right: 0; }}
    .header > tbody > tr > td:last-child {{ border-left: 0; }}
    .meta {{ width: 42mm; font-size: 11px; }}
    .meta .label {{ width: 16mm; background: #f3f4f6; font-weight: 800; text-align: center; }}
    .title-cell {{ text-align: center; }}
    .title-fa {{ font-size: 21px; font-weight: 900; letter-spacing: 0; }}
    .title-en {{ margin-top: 1px; direction: ltr; font-size: 12px; font-weight: 900; }}
    .subtitle {{ font-size: 11px; color: #374151; }}
    .logo-box {{
      height: 24mm;
      border: 1px solid #8b95a1;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      background: #fafafa;
    }}
    .section-title {{
      background: #d6d6d6;
      border: 1px solid #1f2937;
      border-bottom: 0;
      margin-top: 4mm;
      padding: 4px 6px;
      text-align: center;
      font-weight: 900;
    }}
    .info td:nth-child(odd) {{ width: 25mm; background: #f2f2f2; font-weight: 900; text-align: center; }}
    .info td:nth-child(even) {{ text-align: right; }}
    .purpose td {{ height: 9mm; text-align: center; font-weight: 700; }}
    .check {{
      display: inline-block;
      width: 10px;
      height: 10px;
      margin-right: 5px;
      border: 1.4px solid #111827;
      vertical-align: -1px;
      background: #fff;
    }}
    .check.is-checked {{ background: #111827; box-shadow: inset 0 0 0 2px #fff; }}
    .docs th {{ font-size: 11px; }}
    .docs td {{ text-align: center; font-size: 10.5px; }}
    .docs .doc-no {{ direction: ltr; font-family: Consolas, 'Courier New', monospace; font-weight: 800; }}
    .docs .doc-title {{ text-align: right; font-size: 10.2px; }}
    .download-link {{ color: #0f5f9e; font-weight: 900; text-decoration: underline; }}
    .empty-row {{ height: 26mm; color: #64748b; font-weight: 800; }}
    .signatures td {{ height: 23mm; text-align: center; font-weight: 800; }}
    .muted {{ color: #64748b; font-size: 10px; }}
    .ltr {{ direction: ltr; unicode-bidi: embed; }}
    @media print {{
      body {{ background: #fff; }}
      .sheet {{ width: 210mm; min-height: 297mm; margin: 0; box-shadow: none; }}
    }}
  </style>
</head>
<body>
  <main class="sheet">
    <header class="print-header">
    <table class="header">
      <tr>
        <td class="meta">
          <table>
            <tr><td class="label">شماره</td><td class="ltr">{html_escape(_safe_text(tr.id))}</td></tr>
            <tr><td class="label">ویرایش</td><td>00</td></tr>
            <tr><td class="label">تاریخ</td><td>{html_escape(_format_jalali_date(tr.created_at))}</td></tr>
          </table>
        </td>
        <td class="title-cell">
          <div class="title-fa">برگه ارسال مدارک / ترنسمیتال</div>
          <div class="title-en">DOCUMENT TRANSMITTAL</div>
          <div class="subtitle">{html_escape(project_name)}</div>
        </td>
        <td style="width: 43mm;"><div class="logo-box">لوگوی شرکت</div></td>
      </tr>
    </table>
    </header>

    <section class="print-content">
    <div class="section-title">مشخصات پروژه و ترنسمیتال</div>
    <table class="info">
      <tr><td>نام پروژه</td><td>{html_escape(project_name)}</td><td>شماره پروژه</td><td class="ltr">{html_escape(project_code)}</td></tr>
      <tr><td>از</td><td>{html_escape(sender_label)}</td><td>به</td><td>{html_escape(receiver_label)}</td></tr>
      <tr><td>دیسیپلین</td><td>{html_escape(disciplines)}</td><td>پکیج / ناحیه</td><td>{html_escape(packages)}</td></tr>
      <tr><td>وضعیت</td><td>{html_escape(_status_label(state_record['status']))}</td><td>موضوع</td><td>{html_escape(_display_subject_with_labels(db, tr))}</td></tr>
    </table>

    <div class="section-title">هدف از ارسال</div>
    <table class="purpose">
      <tr>
        <td>{_checkbox_html(purposes['approval'])} جهت تایید</td>
        <td>{_checkbox_html(purposes['review'])} جهت بررسی</td>
        <td>{_checkbox_html(purposes['info'])} جهت اطلاع</td>
        <td>{_checkbox_html(purposes['execution'])} جهت اجرا</td>
        <td>{_checkbox_html(purposes['archive'])} جهت بایگانی</td>
      </tr>
    </table>

    <div class="section-title">فهرست مدارک ارسالی</div>
    <table class="docs">
      <thead>
        <tr>
          <th style="width: 8mm;">ردیف</th>
          <th style="width: 36mm;">شماره مدرک</th>
          <th>عنوان مدرک</th>
          <th style="width: 14mm;">ویرایش</th>
          <th style="width: 18mm;">وضعیت</th>
          <th style="width: 14mm;">تعداد</th>
          <th style="width: 22mm;">فرمت</th>
          <th style="width: 20mm;">دریافت</th>
          <th style="width: 28mm;">توضیحات</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>

    </section>

    <footer class="print-footer">
    <div class="section-title">تایید و دریافت</div>
    <table class="signatures">
      <tr><td>تهیه‌کننده / صادرکننده<br><span class="muted">نام، امضا، تاریخ</span></td><td>کنترل مدارک<br><span class="muted">نام، امضا، تاریخ</span></td><td>دریافت‌کننده<br><span class="muted">نام، امضا، تاریخ</span></td></tr>
    </table>
    </footer>
  </main>
</body>
</html>"""
    return html


def _serialize_transmittal_correspondence_relation(
    row: CorrespondenceExternalRelation,
    correspondence: Correspondence,
) -> Dict[str, object]:
    return {
        "id": f"correspondence_external:{int(row.id or 0)}",
        "relation_id": int(row.id or 0),
        "correspondence_id": int(correspondence.id or 0),
        "reference_no": correspondence.reference_no or f"CORR-{int(correspondence.id or 0)}",
        "subject": correspondence.subject,
        "project_code": correspondence.project_code,
        "direction": correspondence.direction,
        "doc_type": correspondence.doc_type,
        "status": correspondence.status,
        "relation_type": row.relation_type,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _list_transmittal_correspondence_relations(
    db: Session,
    user: User,
    transmittal: Transmittal,
) -> List[Dict[str, object]]:
    query = (
        db.query(CorrespondenceExternalRelation, Correspondence)
        .join(Correspondence, Correspondence.id == CorrespondenceExternalRelation.correspondence_id)
        .filter(
            CorrespondenceExternalRelation.target_entity_type == "transmittal",
            CorrespondenceExternalRelation.target_entity_id == str(transmittal.id),
        )
    )
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=Correspondence.project_code,
    )
    rows = query.order_by(
        CorrespondenceExternalRelation.created_at.desc(),
        CorrespondenceExternalRelation.id.desc(),
    ).all()
    return [_serialize_transmittal_correspondence_relation(row, corr) for row, corr in rows]


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
        if doc.deleted_at is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Document {doc.doc_number} is deleted and cannot be used",
            )
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
    for doc_item in documents:
        doc_code = doc_item.document_code.strip()
        doc = docs_by_code.get(doc_code)
        if doc is None:
            continue
        selected_kind = _normalize_transmittal_file_kind(doc_item.file_kind)
        revision = _document_revision_by_code(doc, doc_item.revision)
        options = _revision_file_options(revision)
        allowed = {str(option.get("value") or "").strip().lower() for option in options}
        if allowed and selected_kind not in allowed:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Selected file_kind '{doc_item.file_kind}' is not available for "
                    f"document {doc_code} revision {doc_item.revision or '-'}"
                ),
            )
    return docs_by_code


@router.get("/options")
def get_transmittal_options(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:read")),
):
    del user
    return {"ok": True, **transmittal_options_payload(db, active_only=True)}


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
    query = query.filter(MdrDocument.project_code == project, MdrDocument.deleted_at.is_(None))

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
    output = []
    for doc, rev in rows:
        file_options = _revision_file_options(rev)
        output.append(
            {
                "doc_number": doc.doc_number,
                "doc_title": doc.doc_title_p or doc.doc_title_e or doc.subject or doc.doc_number,
                "project_code": doc.project_code,
                "discipline_code": doc.discipline_code,
                "revision": rev.revision if rev else "00",
                "status": rev.status if rev else "Registered",
                "default_file_kind": _default_file_kind(file_options),
                "file_options": file_options,
            }
        )
    return output


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
        party_labels = _transmittal_party_labels(db, t)
        output.append(
            {
                "id": t.id,
                "transmittal_no": t.id,
                "subject": _display_subject_with_labels(db, t),
                "created_at": t.created_at,
                "doc_count": len(t.docs),
                "status": state_record["status"],
                **party_labels,
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
            file_kind=_normalize_transmittal_file_kind(doc_item.file_kind),
            electronic_copy=doc_item.electronic_copy,
            hard_copy=doc_item.hard_copy,
        )
        db.add(tr_doc)

    try:
        initial_state = STATE_ISSUED if payload.issue_now else STATE_DRAFT
        _set_transmittal_state(new_tr, initial_state)
        if initial_state == STATE_ISSUED and not new_tr.send_date:
            new_tr.send_date = datetime.utcnow().date().isoformat()
        if initial_state == STATE_ISSUED:
            for doc in docs_by_code.values():
                log_document_activity(
                    db,
                    int(doc.id or 0),
                    "transmittal_sent",
                    user,
                    detail=f"transmittal:{transmittal_id}",
                    after_data={
                        "transmittal_id": transmittal_id,
                        "document_code": doc.doc_number,
                    },
                )
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
    correspondence_relations = _list_transmittal_correspondence_relations(db, user, tr)
    party_labels = _transmittal_party_labels(db, tr)
    doc_codes = [str(d.document_code or "").strip() for d in tr.docs if str(d.document_code or "").strip()]
    mdr_rows: dict[str, MdrDocument] = {}
    if doc_codes:
        mdr_rows = {
            row.doc_number: row
            for row in db.query(MdrDocument).filter(MdrDocument.doc_number.in_(doc_codes)).all()
        }
    document_items: List[Dict[str, object]] = []
    for d in tr.docs:
        mdr_doc = mdr_rows.get(str(d.document_code or "").strip())
        revision = _document_revision_by_code(mdr_doc, d.revision) if mdr_doc is not None else None
        file_options = _revision_file_options(revision)
        file_kind = _normalize_transmittal_file_kind(getattr(d, "file_kind", "pdf"))
        document_items.append(
            {
                "document_code": d.document_code,
                "revision": d.revision or "00",
                "status": d.status or "IFA",
                "file_kind": file_kind,
                "file_label": _transmittal_file_label(file_kind),
                "file_options": file_options,
                "electronic_copy": bool(d.electronic_copy),
                "hard_copy": bool(d.hard_copy),
                "document_title": d.document_title,
            }
        )
    return {
        "id": tr.id,
        "transmittal_no": tr.id,
        "project_code": tr.project_code,
        "sender": tr.sender,
        "receiver": tr.receiver,
        **party_labels,
        "subject": _display_subject_with_labels(db, tr),
        "created_at": tr.created_at,
        "status": state_record["status"],
        "void_reason": state_record["void_reason"],
        "voided_by": state_record["voided_by"],
        "voided_at": state_record["voided_at"],
        "documents": document_items,
        "correspondence_relations": correspondence_relations,
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
                file_kind=_normalize_transmittal_file_kind(doc_item.file_kind),
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
    doc_codes = [str(row.document_code or "").strip() for row in (tr.docs or []) if str(row.document_code or "").strip()]
    if doc_codes:
        docs = (
            db.query(MdrDocument)
            .filter(
                MdrDocument.doc_number.in_(doc_codes),
                MdrDocument.project_code == tr.project_code,
            )
            .all()
        )
        for doc in docs:
            log_document_activity(
                db,
                int(doc.id or 0),
                "transmittal_sent",
                user,
                detail=f"transmittal:{tr.id}",
                after_data={
                    "transmittal_id": tr.id,
                    "document_code": doc.doc_number,
                },
            )
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


@router.get("/{transmittal_id}/print-preview", response_class=HTMLResponse)
def print_preview_transmittal(
    transmittal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("transmittal:read")),
):
    tr = db.query(Transmittal).filter(Transmittal.id == transmittal_id).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Transmittal not found")
    enforce_scope_access(db, user, project_code=tr.project_code)
    return HTMLResponse(_render_transmittal_print_html(db, tr))


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

    pdf_buffer = generate_transmittal_pdf(
        _build_transmittal_pdf_payload(db, tr),
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
