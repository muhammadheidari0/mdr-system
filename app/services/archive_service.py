# app/services/archive_service.py
from __future__ import annotations

import os
import re
import io
import secrets
from typing import Any
from datetime import date, datetime, time, timedelta
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func, or_
from fastapi import UploadFile, HTTPException

from app.api.dependencies import enforce_scope_access, has_permission_for_user
from app.db.models import (
    ArchiveFile,
    ArchiveFilePublicShare,
    Block,
    CommItem,
    Correspondence,
    Discipline,
    DocumentActivity,
    DocumentComment,
    DocumentExternalRelation,
    DocumentRelation,
    DocumentRevision,
    DocumentTag,
    DocumentTagAssignment,
    Level,
    MeetingMinute,
    MdrCategory,
    MdrDocument,
    Package,
    PermitQcPermit,
    Phase,
    Project,
    SiteLog,
    Transmittal,
    TransmittalDoc,
)
from app.services import docnum_service, folder_service, mdr_service
from app.services.access_control import resolve_effective_access
from app.services.document_activity_service import (
    log_document_activity,
    serialize_document_snapshot,
)
from app.services.storage import StorageManager
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import (
    enqueue_archive_mirror_job,
    resolve_mirror_enqueue_plan,
    resolve_nextcloud_runtime,
)
from app.services.nextcloud_adapter import NextcloudAdapter

PUBLIC_SHARE_UNAVAILABLE_DETAIL = "این فایل هنوز در Nextcloud قابل اشتراک‌گذاری نیست."
PUBLIC_SHARE_DEFAULT_EXPIRY_DAYS = 60
PUBLIC_SHARE_READY_MIRROR_STATUSES = {"mirrored"}

# ---------------------------------------------------------
# 1. Helper: Calculate Next Revision
# ---------------------------------------------------------
def _calculate_next_revision(current_rev: str) -> str:
    if not current_rev: return "00"
    if current_rev.isdigit():
        try: return f"{int(current_rev) + 1:02d}"
        except: pass
    if len(current_rev) == 1 and current_rev.isalpha():
        if ord(current_rev.upper()) < ord('Z'):
            return chr(ord(current_rev.upper()) + 1)
    return current_rev

# ---------------------------------------------------------
# 2. Helper: Parse Document Code for Components
# ---------------------------------------------------------
def _parse_doc_code(doc_number: str) -> dict | None:
    """
    تجزیه کد سند برای استخراج اجزا.
    فرمت استاندارد: PROJECT-MDR+PHASE+PKG+SERIAL-BLOCK+LEVEL
    مثال: T202-ECAR0101-TGEN
    """
    if not doc_number:
        return None

    try:
        parts = str(doc_number).strip().upper().split("-")
        if len(parts) < 3:
            return None

        project_code = parts[0].strip()
        middle = parts[1].strip()  # ECAR0101
        suffix = parts[2].strip()  # TGEN

        if not project_code or len(middle) < 3 or len(suffix) < 2:
            return None

        mdr_c = middle[0]
        phase_c = middle[1]

        # Format after MDR+Phase is usually PKG + SERIAL(2).
        core = middle[2:]
        serial_match = re.search(r"(\d{2})$", core)
        serial_c = serial_match.group(1) if serial_match else ""
        pkg_full = core[:-2] if serial_match else core
        pkg_full = pkg_full or core or "00"
        disc_match = re.match(r"^([A-Z]+?)(\d.*)$", pkg_full)
        if disc_match:
            disc_c = disc_match.group(1)
            pkg_c = disc_match.group(2)
        else:
            disc_c = pkg_full[:2] if len(pkg_full) >= 2 else "GN"
            pkg_c = pkg_full
        block_c = suffix[0]
        level_c = suffix[1:] or "GEN"

        return {
            "project_code": project_code,
            "mdr_code": mdr_c,
            "phase_code": phase_c,
            "discipline_code": disc_c,
            "package_code": pkg_c,
            "serial": serial_c,
            "block": block_c,
            "level_code": level_c,
        }
    except Exception as e:
        print(f"Error parsing doc code: {e}")
        return None


def _normalize_archive_file_kind(value: str | None) -> str:
    kind = str(value or "").strip().lower()
    if kind in {"pdf", "native"}:
        return kind
    return "pdf"


def _normalize_lookup_code(value: Any, default: str = "") -> str:
    text = str(value or "").strip().upper()
    return text or str(default or "").strip().upper()


def _archive_file_name_for_document(
    document: MdrDocument,
    *,
    revision_code: str,
    extension: str,
) -> str:
    raw_title = document.doc_title_e or document.subject or "Untitled"
    safe_title = folder_service.safe_name(raw_title)
    if len(safe_title) > 100:
        safe_title = safe_title[:100]
    clean_extension = str(extension or "").strip()
    if clean_extension and not clean_extension.startswith("."):
        clean_extension = f".{clean_extension}"
    return f"{document.doc_number}_{safe_title}_Rev{revision_code}{clean_extension}"


def _document_project_folder(document: MdrDocument) -> str:
    safe_project_code = folder_service.safe_name(document.project_code or "project") or "project"
    project_name = ""
    if document.project:
        project_name = document.project.name_e or document.project.name_p or ""
    safe_project_name = folder_service.safe_name(project_name)
    if safe_project_name and safe_project_name.lower() != "unk":
        return folder_service.safe_name(f"{safe_project_code} - {safe_project_name}") or safe_project_code
    return safe_project_code


def _join_webdav_absolute_path(*segments: str | None) -> str:
    cleaned: list[str] = []
    for segment in segments:
        text = str(segment or "").strip().replace("\\", "/").strip("/")
        if text:
            cleaned.append(text)
    return f"/{'/'.join(cleaned)}"


def _archive_storage_target(
    db: Session,
    document: MdrDocument,
    *,
    revision_code: str,
    extension: str,
    file_kind: str,
    prefer_webdav: bool | None = None,
) -> tuple[StorageManager, str, str]:
    storage = StorageManager(db)
    normalized_kind = _normalize_archive_file_kind(file_kind)
    clean_name = _archive_file_name_for_document(
        document,
        revision_code=str(revision_code or "00").strip() or "00",
        extension=extension,
    )

    proj_name = document.project.name_e if document.project else document.project_code
    mdr_folder = folder_service.get_mdr_folder_name(db, document.mdr_code)

    phase_name = document.phase_code
    if document.phase:
        phase_name = document.phase.name_e or document.phase_code

    disc_name = "General"
    disc_code = document.discipline_code or "GN"
    if document.discipline:
        disc_name = document.discipline.name_e

    pkg_name = "General"
    pkg_code = document.package_code or "00"
    if document.package:
        pkg_name = document.package.name_e or document.package.name_p or document.package_code

    use_webdav = storage._is_webdav_primary_mode() if prefer_webdav is None else bool(prefer_webdav)
    if use_webdav:
        integrations = get_storage_integrations(db)
        runtime = resolve_nextcloud_runtime(integrations)
        root_path = str(runtime.get("root_path") or "")
        mdr_base = storage.get_mdr_webdav_base()
        pkg_folder = folder_service.safe_name(f"{pkg_code} - {pkg_name}") or folder_service.safe_name(pkg_code) or "00"
        absolute_path = _join_webdav_absolute_path(
            mdr_base,
            _document_project_folder(document),
            folder_service.safe_name(phase_name) or "Phase",
            folder_service.safe_name(disc_code) or "GN",
            pkg_folder,
            normalized_kind,
            clean_name,
        )
        relative_path = StorageManager.relativize_webdav_path(absolute_path, root_path)
        return storage, clean_name, f"webdav://{relative_path}"

    target_folder = storage.get_mdr_path(
        project_code=document.project_code,
        project_name=proj_name,
        mdr_folder_name=mdr_folder,
        phase_name=phase_name,
        phase_code=document.phase_code or phase_name,
        disc_name=disc_name,
        disc_code=disc_code,
        pkg_name=pkg_name,
        pkg_code=pkg_code,
        package_name=pkg_name,
        file_kind=normalized_kind,
    )
    return storage, clean_name, os.path.join(target_folder, folder_service.safe_name(clean_name))


def _nextcloud_adapter(db: Session) -> NextcloudAdapter:
    integrations = get_storage_integrations(db)
    runtime = resolve_nextcloud_runtime(integrations)
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


def _webdav_relative_path(stored_path: str) -> str:
    return str(stored_path or "").strip().replace("webdav://", "", 1)


def _normalize_nextcloud_share_path(path: str | None) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        return ""
    try:
        return NextcloudAdapter.normalize_browse_path(raw)
    except ValueError:
        return ""


def _resolve_nextcloud_share_path(file_record: ArchiveFile | None) -> dict[str, Any]:
    if not file_record:
        return {
            "path": None,
            "source": None,
            "status": "missing_remote_path",
            "supported": False,
        }

    stored_path = str(getattr(file_record, "stored_path", "") or "").strip()
    if stored_path.startswith("webdav://"):
        relative_path = _normalize_nextcloud_share_path(_webdav_relative_path(stored_path))
        if relative_path:
            return {
                "path": relative_path,
                "source": "primary_nextcloud",
                "status": "available",
                "supported": True,
            }
        return {
            "path": None,
            "source": None,
            "status": "missing_remote_path",
            "supported": False,
        }

    mirror_provider = str(getattr(file_record, "mirror_provider", "") or "").strip().lower()
    if mirror_provider == "nextcloud":
        mirror_status = str(getattr(file_record, "mirror_status", "") or "").strip().lower()
        remote_id = _normalize_nextcloud_share_path(getattr(file_record, "mirror_remote_id", None))
        if mirror_status not in PUBLIC_SHARE_READY_MIRROR_STATUSES:
            return {
                "path": remote_id or None,
                "source": "mirror_nextcloud" if remote_id else None,
                "status": "mirror_not_ready",
                "supported": False,
            }
        if not remote_id:
            return {
                "path": None,
                "source": None,
                "status": "missing_remote_path",
                "supported": False,
            }
        return {
            "path": remote_id,
            "source": "mirror_nextcloud",
            "status": "available",
            "supported": True,
        }

    return {
        "path": None,
        "source": None,
        "status": "not_nextcloud",
        "supported": False,
    }


def public_share_support_payload(file_record: ArchiveFile | None) -> dict[str, Any]:
    resolved = _resolve_nextcloud_share_path(file_record)
    return {
        "public_share_supported": bool(resolved.get("supported")),
        "public_share_source": resolved.get("source") if resolved.get("supported") else None,
        "public_share_status": str(resolved.get("status") or "missing_remote_path"),
    }


def _active_archive_public_share(db: Session, file_id: int) -> ArchiveFilePublicShare | None:
    now = datetime.utcnow()
    return (
        db.query(ArchiveFilePublicShare)
        .filter(
            ArchiveFilePublicShare.file_id == int(file_id or 0),
            ArchiveFilePublicShare.provider == "nextcloud",
            ArchiveFilePublicShare.revoked_at.is_(None),
            or_(ArchiveFilePublicShare.expires_at.is_(None), ArchiveFilePublicShare.expires_at > now),
        )
        .order_by(ArchiveFilePublicShare.created_at.desc(), ArchiveFilePublicShare.id.desc())
        .first()
    )


def serialize_archive_public_share(
    row: ArchiveFilePublicShare | None,
    *,
    password: str | None = None,
) -> dict[str, Any] | None:
    if not row:
        return None
    payload = {
        "id": int(row.id or 0),
        "file_id": int(row.file_id or 0),
        "provider": row.provider,
        "provider_share_id": row.provider_share_id,
        "token": row.token,
        "url": row.share_url,
        "resolved_path": row.resolved_path,
        "source": row.source,
        "permissions": int(row.permissions or 1),
        "password_set": bool(row.password_set),
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }
    if password is not None:
        payload["password"] = password
    return payload


def _load_archive_file_for_public_share(
    db: Session,
    file_id: int,
    user: Any,
) -> tuple[ArchiveFile, MdrDocument]:
    row = (
        db.query(ArchiveFile)
        .options(joinedload(ArchiveFile.document_revision).joinedload(DocumentRevision.document))
        .filter(ArchiveFile.id == int(file_id or 0), ArchiveFile.deleted_at.is_(None))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found.")
    revision = row.document_revision
    document = revision.document if revision else None
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only.")
    return row, document


def _parse_public_share_expire_date(value: Any) -> date:
    if isinstance(value, datetime):
        day = value.date()
    elif isinstance(value, date):
        day = value
    else:
        raw = str(value or "").strip()
        if raw:
            try:
                day = date.fromisoformat(raw[:10])
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Invalid expire_date format (YYYY-MM-DD expected).") from exc
        else:
            day = date.today() + timedelta(days=PUBLIC_SHARE_DEFAULT_EXPIRY_DAYS)
    if day < date.today():
        raise HTTPException(status_code=422, detail="expire_date cannot be in the past.")
    return day


def _generate_public_share_password() -> str:
    return secrets.token_urlsafe(15)


def _configured_public_share_password(db: Session) -> str:
    integrations = get_storage_integrations(db)
    return str((integrations.get("nextcloud") or {}).get("public_share_password") or "").strip()


def _public_share_password_required(db: Session) -> bool:
    integrations = get_storage_integrations(db)
    return bool((integrations.get("nextcloud") or {}).get("public_share_password_required", True))


def get_archive_file_public_share(
    db: Session,
    file_id: int,
    user: Any,
) -> dict[str, Any]:
    file_record, _document = _load_archive_file_for_public_share(db, file_id, user)
    support = public_share_support_payload(file_record)
    return {
        "ok": True,
        "file_id": int(file_record.id or 0),
        **support,
        "public_share": serialize_archive_public_share(
            _active_archive_public_share(db, int(file_record.id or 0))
        ),
    }


def create_archive_file_public_share(
    db: Session,
    file_id: int,
    user: Any,
    *,
    expire_date: Any = None,
    password: str | None = None,
    regenerate: bool = False,
) -> dict[str, Any]:
    file_record, document = _load_archive_file_for_public_share(db, file_id, user)
    resolved = _resolve_nextcloud_share_path(file_record)
    support = public_share_support_payload(file_record)
    if not resolved.get("supported") or not resolved.get("path"):
        raise HTTPException(status_code=409, detail=PUBLIC_SHARE_UNAVAILABLE_DETAIL)

    adapter = _nextcloud_adapter(db)
    remote_path = str(resolved.get("path") or "").strip()
    if not adapter.file_exists(remote_path):
        raise HTTPException(status_code=409, detail=PUBLIC_SHARE_UNAVAILABLE_DETAIL)

    active = _active_archive_public_share(db, int(file_record.id or 0))
    if active and not regenerate:
        return {
            "ok": True,
            "file_id": int(file_record.id or 0),
            **support,
            "public_share": serialize_archive_public_share(active),
        }

    if active and regenerate:
        try:
            adapter.delete_share(active.provider_share_id)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Failed to revoke existing Nextcloud share.") from exc
        active.revoked_at = datetime.utcnow()
        active.revoked_by_id = getattr(user, "id", None)

    expires_day = _parse_public_share_expire_date(expire_date)
    expires_at = datetime.combine(expires_day, time.max.replace(microsecond=0))
    manual_password = str(password or "").strip()
    if manual_password:
        share_password: str | None = manual_password
    elif _public_share_password_required(db):
        share_password = _configured_public_share_password(db) or _generate_public_share_password()
    else:
        share_password = None
    try:
        created = adapter.create_public_share(
            remote_relative_path=remote_path,
            password=share_password,
            expire_date=expires_day.isoformat(),
            permissions=1,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Failed to create Nextcloud public share.") from exc

    provider_share_id = str(created.get("provider_share_id") or "").strip()
    share_url = str(created.get("url") or "").strip()
    if not provider_share_id or not share_url:
        raise HTTPException(status_code=502, detail="Nextcloud did not return a valid public share.")

    row = ArchiveFilePublicShare(
        file_id=int(file_record.id or 0),
        provider="nextcloud",
        provider_share_id=provider_share_id,
        token=created.get("token"),
        share_url=share_url,
        resolved_path=remote_path,
        source=str(resolved.get("source") or ""),
        permissions=1,
        password_set=bool(share_password),
        expires_at=expires_at,
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    log_document_activity(
        db,
        int(document.id or 0),
        "public_share_renewed" if active and regenerate else "public_share_created",
        user,
        detail=f"Public share created for {file_record.original_name}",
        after_data={
            "file_id": int(file_record.id or 0),
            "source": row.source,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "provider_share_id": row.provider_share_id,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "file_id": int(file_record.id or 0),
        **support,
        "public_share": serialize_archive_public_share(row, password=share_password),
    }


def revoke_archive_file_public_share(
    db: Session,
    file_id: int,
    user: Any,
) -> dict[str, Any]:
    file_record, document = _load_archive_file_for_public_share(db, file_id, user)
    row = _active_archive_public_share(db, int(file_record.id or 0))
    if not row:
        raise HTTPException(status_code=404, detail="Public share not found.")
    adapter = _nextcloud_adapter(db)
    try:
        adapter.delete_share(row.provider_share_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Failed to revoke Nextcloud public share.") from exc
    row.revoked_at = datetime.utcnow()
    row.revoked_by_id = getattr(user, "id", None)
    row.updated_at = datetime.utcnow()
    log_document_activity(
        db,
        int(document.id or 0),
        "public_share_revoked",
        user,
        detail=f"Public share revoked for {file_record.original_name}",
        before_data={
            "file_id": int(file_record.id or 0),
            "source": row.source,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "provider_share_id": row.provider_share_id,
        },
    )
    db.commit()
    return {
        "ok": True,
        "file_id": int(file_record.id or 0),
        **public_share_support_payload(file_record),
        "public_share": None,
        "revoked_share": serialize_archive_public_share(row),
    }


def _delete_physical_file(db: Session, stored_path: str | None) -> None:
    path_value = str(stored_path or "").strip()
    if not path_value:
        return
    if path_value.startswith("webdav://"):
        adapter = _nextcloud_adapter(db)
        relative_path = _webdav_relative_path(path_value)
        if not adapter.file_exists(relative_path):
            return
        if not adapter.delete_file(relative_path):
            raise HTTPException(status_code=500, detail="Failed to delete file from WebDAV storage.")
        return
    if os.path.exists(path_value):
        os.remove(path_value)


def _move_physical_file(db: Session, source_path: str, target_path: str) -> None:
    source = str(source_path or "").strip()
    target = str(target_path or "").strip()
    if not source or not target or source == target:
        return
    if source.startswith("webdav://") or target.startswith("webdav://"):
        if not source.startswith("webdav://") or not target.startswith("webdav://"):
            raise HTTPException(status_code=500, detail="Cannot move file across local and WebDAV storage modes.")
        adapter = _nextcloud_adapter(db)
        source_relative = _webdav_relative_path(source)
        target_relative = _webdav_relative_path(target)
        if not adapter.file_exists(source_relative):
            raise HTTPException(status_code=404, detail="Source file not found in WebDAV storage.")
        if adapter.file_exists(target_relative):
            raise HTTPException(status_code=409, detail="Target archive file already exists.")
        payload = b"".join(adapter.download_file_stream(source_relative))
        target_folder = "/".join(target_relative.strip("/").split("/")[:-1])
        if target_folder:
            adapter.ensure_path(target_folder)
        uploaded = False
        try:
            adapter.upload_file_from_stream(file_stream=io.BytesIO(payload), remote_relative_path=target_relative)
            uploaded = True
            if not adapter.delete_file(source_relative):
                raise HTTPException(status_code=500, detail="Failed to delete old WebDAV file after move.")
        except Exception:
            if uploaded:
                try:
                    adapter.delete_file(target_relative)
                except Exception:
                    pass
            raise
        return

    if not os.path.exists(source):
        raise HTTPException(status_code=404, detail="Source archive file not found on disk.")
    if os.path.exists(target):
        raise HTTPException(status_code=409, detail="Target archive file already exists.")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.replace(source, target)


def _canonical_subject_text(subject_e: str | None, subject_p: str | None) -> str:
    p = str(subject_p or "").strip()
    if p:
        return p
    return str(subject_e or "").strip()


def _subject_pair_for_titles(subject_e: str | None, subject_p: str | None) -> tuple[str, str]:
    subject_value = _canonical_subject_text(subject_e, subject_p)
    return subject_value, subject_value


def _active_mdr_code_or_422(db: Session, value: Any) -> str:
    code = str(value or "").strip().upper()
    if not code:
        raise HTTPException(status_code=422, detail="MDR code is required.")
    exists = (
        db.query(MdrCategory.code)
        .filter(MdrCategory.code == code, MdrCategory.is_active.is_(True))
        .first()
    )
    if not exists:
        raise HTTPException(status_code=422, detail="MDR code is not active or does not exist.")
    return code


def _subject_storage(subject_e: str | None, subject_p: str | None) -> str:
    return _canonical_subject_text(subject_e, subject_p)


def _find_subject_conflict(
    db: Session,
    *,
    project_code: str | None,
    subject: str | None,
    exclude_document_id: int,
) -> MdrDocument | None:
    target = mdr_service._normalize_subject_for_key(subject)
    if not target:
        return None
    rows = (
        db.query(MdrDocument)
        .filter(MdrDocument.project_code == str(project_code or "").strip().upper())
        .filter(MdrDocument.id != int(exclude_document_id or 0))
        .filter(MdrDocument.deleted_at.is_(None))
        .all()
    )
    for row in rows:
        if mdr_service._normalize_subject_for_key(row.subject) == target:
            return row
    return None


def _set_subject_and_rebuild_titles(doc: MdrDocument, db: Session, subject: str | None) -> None:
    subject_value = str(subject or "").strip()
    full_e, full_p = mdr_service.build_document_titles(
        db,
        discipline_code=str(doc.discipline_code or "").strip().upper(),
        package_code=str(doc.package_code or "").strip().upper(),
        block_code=str(doc.block or "").strip().upper(),
        level_code=str(doc.level_code or "").strip().upper(),
        subject_e=subject_value,
        subject_p=subject_value,
    )
    doc.doc_title_e = full_e
    doc.doc_title_p = full_p
    doc.subject = subject_value


def _refresh_doc_titles_from_subjects(doc: MdrDocument, db: Session, subject_e: str | None, subject_p: str | None) -> None:
    title_e, title_p = _subject_pair_for_titles(subject_e, subject_p)
    if not title_e and not title_p:
        return
    full_e, full_p = mdr_service.build_document_titles(
        db,
        discipline_code=str(doc.discipline_code or "").strip().upper(),
        package_code=str(doc.package_code or "").strip().upper(),
        block_code=str(doc.block or "").strip().upper(),
        level_code=str(doc.level_code or "").strip().upper(),
        subject_e=title_e,
        subject_p=title_p,
    )
    doc.doc_title_e = full_e
    doc.doc_title_p = full_p
    doc.subject = _subject_storage(title_e, title_p)


def _scope_subjectless_existing_from_meta(db: Session, meta_data: dict) -> MdrDocument | None:
    return mdr_service.find_subjectless_document_by_scope(
        db,
        project_code=str(meta_data.get("project_code") or "").strip().upper(),
        mdr_code=str(meta_data.get("mdr_code") or "X").strip().upper() or "X",
        phase_code=str(meta_data.get("phase") or "X").strip().upper() or "X",
        discipline_code=str(meta_data.get("discipline") or "XX").strip().upper() or "XX",
        package_code=str(meta_data.get("package") or "").strip().upper(),
        block=str(meta_data.get("block") or "").strip().upper(),
        level_code=str(meta_data.get("level") or "GEN").strip().upper() or "GEN",
    )


def _subjectless_expected_doc_number_from_meta(db: Session, meta_data: dict) -> str:
    doc_number, _ = docnum_service.generate_subjectless_doc_number(
        db,
        project_code=str(meta_data.get("project_code") or "").strip().upper(),
        mdr_code=str(meta_data.get("mdr_code") or "X").strip().upper() or "X",
        phase_code=str(meta_data.get("phase") or "X").strip().upper() or "X",
        discipline_code=str(meta_data.get("discipline") or "XX").strip().upper() or "XX",
        pkg_code=str(meta_data.get("package") or "").strip().upper(),
        block=str(meta_data.get("block") or "").strip().upper(),
        level=str(meta_data.get("level") or "GEN").strip().upper() or "GEN",
        start_serial=1,
    )
    return str(doc_number or "").strip().upper()

# ---------------------------------------------------------
# 3. Get Document Info (Main Logic Updated)
# ---------------------------------------------------------
def get_document_status_info(db: Session, doc_number: str, subject_e: str = "", subject_p: str = ""):
    """
    Return document status only (no auto-create side effect).
    """
    doc_number = str(doc_number or "").strip().upper()
    parsed_doc = _parse_doc_code(doc_number)
    if not doc_number:
        return {
            "exists": False,
            "can_register": False,
            "msg": "Document number is empty.",
            "parsed": None,
        }

    doc = (
        db.query(MdrDocument)
        .filter(
            MdrDocument.doc_number == doc_number,
            MdrDocument.deleted_at.is_(None),
        )
        .first()
    )
    if not doc:
        return {
            "exists": False,
            "can_register": bool(parsed_doc),
            "msg": "Document not found in MDR registry.",
            "parsed": parsed_doc,
        }

    last_rev = (
        db.query(DocumentRevision)
        .filter(DocumentRevision.document_id == doc.id)
        .order_by(desc(DocumentRevision.created_at))
        .first()
    )

    current_rev_code = last_rev.revision if last_rev else "N/A"
    current_status = last_rev.status if last_rev else "Registered"
    suggested = _calculate_next_revision(last_rev.revision) if last_rev else "00"

    return {
        "exists": True,
        "document_id": doc.id,
        "doc_number": doc.doc_number,
        "title": doc.doc_title_e or doc.subject or "Untitled",
        "last_revision": current_rev_code,
        "last_status": current_status,
        "next_revision_suggestion": suggested,
        "msg_success": None,
        "is_new_document": False,
        "can_register": False,
        "parsed": {
            "project_code": doc.project_code,
            "mdr_code": doc.mdr_code,
            "phase_code": doc.phase_code,
            "discipline_code": doc.discipline_code,
            "package_code": doc.package_code,
            "serial": (parsed_doc or {}).get("serial", ""),
            "block": doc.block,
            "level_code": doc.level_code,
        },
    }


def _archive_file_sort_key(row: ArchiveFile | None) -> tuple[str, str, int]:
    if not row:
        return ("", "", 0)
    return (
        row.uploaded_at.isoformat() if row.uploaded_at else "",
        row.revision or "",
        int(row.id or 0),
    )


def _normalize_tag_name(name: str | None) -> str:
    return " ".join(str(name or "").strip().split())


def _preview_supported(row: ArchiveFile | None) -> bool:
    if not row or row.deleted_at is not None:
        return False
    mime_type = str(row.mime_type or row.detected_mime or "").strip().lower()
    return mime_type.startswith("image/") or mime_type in {"application/pdf", "application/x-pdf"} or str(
        row.file_kind or ""
    ).strip().lower() == "pdf"


def normalize_user_role(user: Any) -> str:
    try:
        return str(resolve_effective_access(user).effective_role or "").strip().lower()
    except Exception:
        return str(getattr(user, "role", "") or "").strip().lower()


def resolve_document_latest_revision(document: MdrDocument | None) -> DocumentRevision | None:
    if not document:
        return None
    revisions = list(document.revisions or [])
    if not revisions:
        return None
    revisions.sort(
        key=lambda row: (
            row.created_at.isoformat() if row.created_at else "",
            int(row.id or 0),
        ),
        reverse=True,
    )
    return revisions[0]


def resolve_document_preview_file(document: MdrDocument | None) -> ArchiveFile | None:
    if not document:
        return None
    files: list[ArchiveFile] = []
    for revision in document.revisions or []:
        for archive_file in revision.archive_files or []:
            if archive_file.deleted_at is None:
                files.append(archive_file)
    if not files:
        return None
    pdf_candidates = [
        row
        for row in files
        if str(row.mime_type or row.detected_mime or "").strip().lower() in {"application/pdf", "application/x-pdf"}
        or str(row.file_kind or "").strip().lower() == "pdf"
    ]
    image_candidates = [
        row for row in files if str(row.mime_type or row.detected_mime or "").strip().lower().startswith("image/")
    ]
    if pdf_candidates:
        pdf_candidates.sort(key=_archive_file_sort_key, reverse=True)
        return pdf_candidates[0]
    if image_candidates:
        image_candidates.sort(key=_archive_file_sort_key, reverse=True)
        return image_candidates[0]
    return None


def _latest_live_file(document: MdrDocument | None) -> ArchiveFile | None:
    if not document:
        return None
    files: list[ArchiveFile] = []
    for revision in document.revisions or []:
        for archive_file in revision.archive_files or []:
            if archive_file.deleted_at is None:
                files.append(archive_file)
    if not files:
        return None
    files.sort(key=_archive_file_sort_key, reverse=True)
    return files[0]


def _comment_payload_tree(rows: list[DocumentComment]) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            row.created_at.isoformat() if row.created_at else "",
            int(row.id or 0),
        ),
    )
    items: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in ordered:
        payload = {
            "id": int(row.id or 0),
            "document_id": int(row.document_id or 0),
            "parent_id": int(row.parent_id or 0) or None,
            "author_id": int(row.author_id or 0) or None,
            "author_name": row.author_name,
            "author_email": row.author_email,
            "body": None if row.deleted_at else row.body,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
            "is_deleted": bool(row.deleted_at),
            "children": [],
        }
        items[payload["id"]] = payload
        parent_id = payload["parent_id"]
        if parent_id and parent_id in items:
            items[parent_id]["children"].append(payload)
        else:
            roots.append(payload)
    return roots


def _document_capabilities(db: Session, document: MdrDocument, user: Any) -> dict[str, bool]:
    is_deleted = bool(document.deleted_at)
    return {
        "can_edit": bool(has_permission_for_user(db, user, "documents:update") and not is_deleted),
        "can_delete": bool(has_permission_for_user(db, user, "documents:delete") and not is_deleted),
        "can_comment": bool(has_permission_for_user(db, user, "documents:comment_create") and not is_deleted),
        "can_manage_relations": bool(
            has_permission_for_user(db, user, "documents:relation_manage") and not is_deleted
        ),
        "can_manage_tags": bool(has_permission_for_user(db, user, "documents:tag_manage") and not is_deleted),
        "can_reclassify": bool(has_permission_for_user(db, user, "documents:reclassify") and not is_deleted),
        "can_replace_files": bool(has_permission_for_user(db, user, "archive:update") and not is_deleted),
        "can_share_public": bool(has_permission_for_user(db, user, "archive:share") and not is_deleted),
    }


def get_document_detail(db: Session, document_id: int, user: Any) -> dict[str, Any]:
    document = (
        db.query(MdrDocument)
        .options(
            joinedload(MdrDocument.project),
            joinedload(MdrDocument.phase),
            joinedload(MdrDocument.discipline),
            joinedload(MdrDocument.package),
            joinedload(MdrDocument.level),
            joinedload(MdrDocument.updated_by),
            joinedload(MdrDocument.deleted_by),
            joinedload(MdrDocument.revisions).joinedload(DocumentRevision.archive_files),
            joinedload(MdrDocument.comments),
            joinedload(MdrDocument.activities),
            joinedload(MdrDocument.outgoing_relations).joinedload(DocumentRelation.target_document),
            joinedload(MdrDocument.incoming_relations).joinedload(DocumentRelation.source_document),
            joinedload(MdrDocument.tag_assignments).joinedload(DocumentTagAssignment.tag),
        )
        .filter(MdrDocument.id == int(document_id))
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    latest_revision = resolve_document_latest_revision(document)
    preview_file = resolve_document_preview_file(document)
    latest_file = _latest_live_file(document)
    external_relations = (
        db.query(DocumentExternalRelation)
        .filter(DocumentExternalRelation.source_document_id == int(document.id or 0))
        .order_by(DocumentExternalRelation.created_at.desc(), DocumentExternalRelation.id.desc())
        .all()
    )
    revisions = sorted(
        list(document.revisions or []),
        key=lambda row: (
            row.created_at.isoformat() if row.created_at else "",
            int(row.id or 0),
        ),
        reverse=True,
    )
    revision_payload = []
    for revision in revisions:
        files = [
            row
            for row in sorted(revision.archive_files or [], key=_archive_file_sort_key, reverse=True)
            if row.deleted_at is None
        ]
        revision_payload.append(
            {
                "revision_id": int(revision.id or 0),
                "revision": revision.revision,
                "status": revision.status,
                "created_at": revision.created_at.isoformat() if revision.created_at else None,
                "files": [
                    {
                        "id": int(row.id or 0),
                        "name": row.original_name,
                        "mime_type": row.mime_type,
                        "detected_mime": row.detected_mime,
                        "size_bytes": row.size_bytes,
                        "file_kind": row.file_kind,
                        "status": row.status,
                        "is_primary": bool(row.is_primary),
                        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
                        **public_share_support_payload(row),
                        "public_share": serialize_archive_public_share(
                            _active_archive_public_share(db, int(row.id or 0))
                        ),
                    }
                    for row in files
                ],
            }
        )
    return {
        "document": document,
        "latest_revision": latest_revision,
        "latest_files": {
            "preview": preview_file,
            "latest": latest_file,
        },
        "preview_meta": {
            "has_preview": bool(preview_file),
            "supported": _preview_supported(preview_file),
            "file_id": int(preview_file.id or 0) if preview_file else None,
            "mime_type": preview_file.mime_type if preview_file else None,
            "detected_mime": preview_file.detected_mime if preview_file else None,
            "name": preview_file.original_name if preview_file else None,
        },
        "counts": {
            "revisions": len(revisions),
            "comments": len(document.comments or []),
            "activities": len(document.activities or []),
            "relations": len(document.outgoing_relations or [])
            + len(document.incoming_relations or [])
            + len(external_relations),
            "tags": len(document.tag_assignments or []),
        },
        "capabilities": _document_capabilities(db, document, user),
        "is_deleted": bool(document.deleted_at),
        "revisions": revision_payload,
        "comments": _comment_payload_tree(list(document.comments or [])),
        "activities": sorted(
            list(document.activities or []),
            key=lambda row: (
                row.created_at.isoformat() if row.created_at else "",
                int(row.id or 0),
            ),
            reverse=True,
        ),
        "relations": {
            "outgoing": [
                row for row in document.outgoing_relations or [] if getattr(row.target_document, "deleted_at", None) is None
            ] + external_relations,
            "incoming": [
                row for row in document.incoming_relations or [] if getattr(row.source_document, "deleted_at", None) is None
            ],
        },
        "tags": [row for row in document.tag_assignments or [] if getattr(row.tag, "id", None)],
        "transmittals": list_document_transmittals(db, int(document.id or 0), user=user, skip=0, limit=20)["data"],
    }


def update_document_metadata(db: Session, document_id: int, updates: dict[str, Any], user: Any) -> MdrDocument:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    allowed_fields = {"subject", "notes"}
    unexpected = sorted(str(key) for key in (updates or {}) if key not in allowed_fields)
    if unexpected:
        raise HTTPException(
            status_code=422,
            detail=f"Fields are not editable here: {', '.join(unexpected)}",
        )
    before = serialize_document_snapshot(document)
    if "subject" in (updates or {}):
        subject_value = str((updates or {}).get("subject") or "").strip()
        conflict = _find_subject_conflict(
            db,
            project_code=document.project_code,
            subject=subject_value,
            exclude_document_id=int(document.id or 0),
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Subject already exists for document {conflict.doc_number}.",
            )
        _set_subject_and_rebuild_titles(document, db, subject_value)
    if "notes" in (updates or {}):
        document.notes = str((updates or {}).get("notes") or "").strip()
    document.updated_at = datetime.utcnow()
    document.updated_by_id = getattr(user, "id", None)
    after = serialize_document_snapshot(document)
    log_document_activity(
        db,
        int(document.id or 0),
        "metadata_updated",
        user,
        before_data=before,
        after_data=after,
    )
    db.commit()
    db.refresh(document)
    return document


def _extract_serial_from_scope(doc_number: str, prefix: str, suffix: str) -> int | None:
    value = str(doc_number or "").strip().upper()
    if not value.startswith(prefix):
        return None
    middle = value[len(prefix) :]
    if suffix and middle.endswith(suffix):
        middle = middle[: -len(suffix)]
    if not re.fullmatch(r"\d+", middle or ""):
        return None
    return int(middle)


def _validate_reclassification_payload(db: Session, payload: dict[str, Any]) -> dict[str, str]:
    target = {
        "project_code": _normalize_lookup_code(payload.get("project_code")),
        "mdr_code": _normalize_lookup_code(payload.get("mdr_code")),
        "phase_code": _normalize_lookup_code(payload.get("phase_code"), "X"),
        "discipline_code": _normalize_lookup_code(payload.get("discipline_code")),
        "package_code": _normalize_lookup_code(payload.get("package_code"), "00"),
        "block": _normalize_lookup_code(payload.get("block")),
        "level_code": _normalize_lookup_code(payload.get("level_code"), "GEN"),
    }
    missing = [key for key, value in target.items() if not value]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required coding fields: {', '.join(missing)}")

    project = (
        db.query(Project)
        .filter(Project.code == target["project_code"], Project.is_active == True)
        .first()
    )
    if not project:
        raise HTTPException(status_code=422, detail="Project code is not valid.")

    category = (
        db.query(MdrCategory)
        .filter(MdrCategory.code == target["mdr_code"], MdrCategory.is_active == True)
        .first()
    )
    if not category:
        raise HTTPException(status_code=422, detail="MDR code is not valid.")

    phase = db.query(Phase).filter(Phase.ph_code == target["phase_code"]).first()
    if not phase:
        raise HTTPException(status_code=422, detail="Phase code is not valid.")

    discipline = db.query(Discipline).filter(Discipline.code == target["discipline_code"]).first()
    if not discipline:
        raise HTTPException(status_code=422, detail="Discipline code is not valid.")

    package_row, resolved_package_code = mdr_service._resolve_package_row(
        db,
        target["discipline_code"],
        target["package_code"],
    )
    if not package_row:
        raise HTTPException(status_code=422, detail="Package code is not valid for selected discipline.")
    target["package_code"] = resolved_package_code

    block = (
        db.query(Block)
        .filter(
            Block.project_code == target["project_code"],
            Block.code == target["block"],
            Block.is_active == True,
        )
        .first()
    )
    if not block:
        raise HTTPException(status_code=422, detail="Block code is not valid for selected project.")

    level = db.query(Level).filter(Level.code == target["level_code"]).first()
    if not level:
        raise HTTPException(status_code=422, detail="Level code is not valid.")

    return target


def _preview_reclassification_for_document(
    db: Session,
    document: MdrDocument,
    payload: dict[str, Any],
    user: Any,
) -> dict[str, Any]:
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    target = _validate_reclassification_payload(db, payload)
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    enforce_scope_access(
        db,
        user,
        project_code=target["project_code"],
        discipline_code=target["discipline_code"],
    )

    conflict = _find_subject_conflict(
        db,
        project_code=target["project_code"],
        subject=document.subject,
        exclude_document_id=int(document.id or 0),
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"Subject already exists for document {conflict.doc_number}.",
        )

    prefix, suffix = docnum_service.build_doc_number_parts(
        project_code=target["project_code"],
        mdr_code=target["mdr_code"],
        phase_code=target["phase_code"],
        discipline_code=target["discipline_code"],
        pkg_code=target["package_code"],
        block=target["block"],
        level=target["level_code"],
    )
    serial = _extract_serial_from_scope(str(document.doc_number or ""), prefix, suffix)
    if serial is None:
        rows = (
            db.query(MdrDocument.doc_number)
            .filter(MdrDocument.id != int(document.id or 0))
            .filter(MdrDocument.doc_number.like(f"{prefix}%{suffix}"))
            .all()
        )
        max_serial = 0
        for (doc_number,) in rows:
            parsed = _extract_serial_from_scope(str(doc_number or ""), prefix, suffix)
            if parsed is not None and parsed > max_serial:
                max_serial = parsed
        serial = max_serial + 1
    serial_str = f"{serial:02d}"
    doc_number = f"{prefix}{serial_str}{suffix}"
    existing = (
        db.query(MdrDocument)
        .filter(MdrDocument.doc_number == doc_number, MdrDocument.id != int(document.id or 0))
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Document number conflict: {doc_number}")

    subject_value = str(document.subject or "").strip()
    title_e, title_p = mdr_service.build_document_titles(
        db,
        discipline_code=target["discipline_code"],
        package_code=target["package_code"],
        block_code=target["block"],
        level_code=target["level_code"],
        subject_e=subject_value,
        subject_p=subject_value,
    )
    return {
        "target": target,
        "doc_number": doc_number,
        "serial": serial_str,
        "doc_title_e": title_e,
        "doc_title_p": title_p,
    }


def preview_document_reclassification(
    db: Session,
    document_id: int,
    payload: dict[str, Any],
    user: Any,
) -> dict[str, Any]:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return _preview_reclassification_for_document(db, document, payload, user)


def _active_archive_files(document: MdrDocument) -> list[ArchiveFile]:
    rows: list[ArchiveFile] = []
    for revision in document.revisions or []:
        for archive_file in revision.archive_files or []:
            if archive_file.deleted_at is None:
                rows.append(archive_file)
    return rows


def _sync_archive_files_after_reclassification(db: Session, document: MdrDocument) -> list[dict[str, Any]]:
    moved: list[tuple[str, str]] = []
    updates: list[dict[str, Any]] = []
    try:
        for archive_file in _active_archive_files(document):
            old_path = str(archive_file.stored_path or "").strip()
            old_name = str(archive_file.original_name or "").strip()
            _, extension = os.path.splitext(old_name or old_path)
            _, clean_name, target_path = _archive_storage_target(
                db,
                document,
                revision_code=str(archive_file.revision or "00").strip() or "00",
                extension=extension,
                file_kind=archive_file.file_kind,
                prefer_webdav=old_path.startswith("webdav://"),
            )
            if old_path != target_path:
                _move_physical_file(db, old_path, target_path)
                moved.append((old_path, target_path))
            archive_file.original_name = clean_name
            archive_file.stored_path = target_path
            archive_file.storage_backend = (
                "nextcloud"
                if target_path.startswith("webdav://")
                else StorageManager(db).resolve_storage_backend_for_path(target_path)
            )
            revision = archive_file.document_revision
            if revision and (
                str(revision.file_path or "").strip() == old_path
                or archive_file.is_primary
                or _normalize_archive_file_kind(archive_file.file_kind) == "pdf"
            ):
                revision.file_path = target_path
                revision.file_name = clean_name
            updates.append(
                {
                    "file_id": int(archive_file.id or 0),
                    "before_path": old_path,
                    "after_path": target_path,
                    "before_name": old_name,
                    "after_name": clean_name,
                }
            )
        return updates
    except Exception:
        for source_path, target_path in reversed(moved):
            try:
                _move_physical_file(db, target_path, source_path)
            except Exception:
                pass
        raise


def reclassify_document(
    db: Session,
    document_id: int,
    payload: dict[str, Any],
    user: Any,
) -> MdrDocument:
    document = (
        db.query(MdrDocument)
        .options(
            joinedload(MdrDocument.project),
            joinedload(MdrDocument.phase),
            joinedload(MdrDocument.discipline),
            joinedload(MdrDocument.package),
            joinedload(MdrDocument.level),
            joinedload(MdrDocument.revisions).joinedload(DocumentRevision.archive_files),
        )
        .filter(MdrDocument.id == int(document_id))
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    moved: list[tuple[str, str]] = []
    try:
        before = serialize_document_snapshot(document)
        preview = _preview_reclassification_for_document(db, document, payload, user)
        target = preview["target"]
        document.project_code = target["project_code"]
        document.mdr_code = target["mdr_code"]
        document.phase_code = target["phase_code"]
        document.discipline_code = target["discipline_code"]
        document.package_code = target["package_code"]
        document.block = target["block"]
        document.level_code = target["level_code"]
        document.doc_number = preview["doc_number"]
        document.doc_title_e = preview["doc_title_e"]
        document.doc_title_p = preview["doc_title_p"]
        document.updated_at = datetime.utcnow()
        document.updated_by_id = getattr(user, "id", None)
        db.flush()
        db.expire(document, ["project", "phase", "discipline", "package", "level", "mdr_category"])
        file_updates = _sync_archive_files_after_reclassification(db, document)
        moved = [(row["before_path"], row["after_path"]) for row in file_updates if row["before_path"] != row["after_path"]]
        after = serialize_document_snapshot(document)
        log_document_activity(
            db,
            int(document.id or 0),
            "document_reclassified",
            user,
            before_data=before,
            after_data={
                **after,
                "archive_files": file_updates,
            },
        )
        db.commit()
        db.refresh(document)
        return document
    except Exception:
        db.rollback()
        for source_path, target_path in reversed(moved):
            try:
                _move_physical_file(db, target_path, source_path)
            except Exception:
                pass
        raise


def replace_archive_file(
    db: Session,
    file_id: int,
    file: UploadFile,
    user: Any,
    *,
    status_code: str | None = None,
) -> ArchiveFile:
    old_file = (
        db.query(ArchiveFile)
        .options(joinedload(ArchiveFile.document_revision).joinedload(DocumentRevision.document))
        .filter(ArchiveFile.id == int(file_id), ArchiveFile.deleted_at.is_(None))
        .first()
    )
    if not old_file or not old_file.document_revision or not old_file.document_revision.document:
        raise HTTPException(status_code=404, detail="File not found")
    revision = old_file.document_revision
    document = revision.document
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )

    old_path = str(old_file.stored_path or "").strip()
    new_file: ArchiveFile | None = None
    try:
        new_file = save_upload_file(
            db=db,
            file=file,
            document_id=int(document.id or 0),
            revision_code=str(old_file.revision or revision.revision or "00").strip() or "00",
            status_code=str(status_code or old_file.status or revision.status or "IFA").strip() or "IFA",
            file_kind=old_file.file_kind,
            is_primary=True if old_file.is_primary is None else bool(old_file.is_primary),
            companion_file_id=old_file.companion_file_id,
            commit=False,
            actor=user,
            log_revision=False,
        )
        now = datetime.utcnow()
        old_file.deleted_at = now
        companions = (
            db.query(ArchiveFile)
            .filter(ArchiveFile.companion_file_id == int(old_file.id or 0), ArchiveFile.deleted_at.is_(None))
            .all()
        )
        for companion in companions:
            companion.companion_file_id = int(new_file.id or 0)
        if revision.file_path == old_path or old_file.is_primary:
            revision.file_path = new_file.stored_path
            revision.file_name = new_file.original_name
        log_document_activity(
            db,
            int(document.id or 0),
            "revision_file_replaced",
            user,
            detail=f"file:{int(old_file.id or 0)}",
            before_data={
                "file_id": int(old_file.id or 0),
                "stored_path": old_file.stored_path,
                "name": old_file.original_name,
            },
            after_data={
                "file_id": int(new_file.id or 0),
                "stored_path": new_file.stored_path,
                "name": new_file.original_name,
                "revision": new_file.revision,
            },
        )
        if old_path and old_path != str(new_file.stored_path or "").strip():
            _delete_physical_file(db, old_path)
        db.commit()
        db.refresh(new_file)
        return new_file
    except Exception:
        db.rollback()
        if new_file is not None:
            try:
                _delete_physical_file(db, new_file.stored_path)
            except Exception:
                pass
        raise


def soft_delete_document(db: Session, document_id: int, user: Any) -> MdrDocument:
    document = (
        db.query(MdrDocument)
        .options(joinedload(MdrDocument.revisions).joinedload(DocumentRevision.archive_files))
        .filter(MdrDocument.id == int(document_id))
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    if document.deleted_at:
        return document
    before = serialize_document_snapshot(document)
    now = datetime.utcnow()
    document.deleted_at = now
    document.deleted_by_id = getattr(user, "id", None)
    document.updated_at = now
    document.updated_by_id = getattr(user, "id", None)
    for revision in document.revisions or []:
        for archive_file in revision.archive_files or []:
            if archive_file.deleted_at is None:
                archive_file.deleted_at = now
    log_document_activity(
        db,
        int(document.id or 0),
        "deleted",
        user,
        before_data=before,
        after_data=serialize_document_snapshot(document),
    )
    db.commit()
    db.refresh(document)
    return document


def apply_transmittal_scope_filters(query: Any, user: Any, db: Session) -> Any:
    from app.api.dependencies import apply_scope_query_filters

    return apply_scope_query_filters(
        query,
        db,
        user,
        project_column=Transmittal.project_code,
    )


def list_document_transmittals(
    db: Session,
    document_id: int,
    *,
    user: Any | None = None,
    skip: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if user is not None:
        enforce_scope_access(
            db,
            user,
            project_code=document.project_code,
            discipline_code=document.discipline_code,
        )
    query = (
        db.query(Transmittal)
        .join(TransmittalDoc, TransmittalDoc.transmittal_id == Transmittal.id)
        .filter(TransmittalDoc.document_code == document.doc_number)
        .order_by(Transmittal.created_at.desc())
    )
    if user is not None:
        query = apply_transmittal_scope_filters(query, user, db)
    total = query.count()
    rows = query.offset(max(0, int(skip or 0))).limit(max(1, int(limit or 20))).all()
    return {
        "ok": True,
        "total": total,
        "data": [
            {
                "id": row.id,
                "transmittal_no": row.id,
                "project_code": row.project_code,
                "status": str(getattr(row, "lifecycle_status", None) or ("issued" if row.send_date else "draft")).lower(),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "sender": row.sender,
                "receiver": row.receiver,
            }
            for row in rows
        ],
    }


def list_document_activity(db: Session, document_id: int, user: Any, skip: int = 0, limit: int = 50) -> dict[str, Any]:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    query = db.query(DocumentActivity).filter(DocumentActivity.document_id == int(document_id))
    total = query.count()
    rows = (
        query.order_by(DocumentActivity.created_at.desc(), DocumentActivity.id.desc())
        .offset(max(0, int(skip or 0)))
        .limit(max(1, int(limit or 50)))
        .all()
    )
    return {"ok": True, "total": total, "data": rows}


def list_document_comments(db: Session, document_id: int, user: Any) -> list[DocumentComment]:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    return (
        db.query(DocumentComment)
        .filter(DocumentComment.document_id == int(document_id))
        .order_by(DocumentComment.created_at.asc(), DocumentComment.id.asc())
        .all()
    )


def create_document_comment(
    db: Session,
    document_id: int,
    body: str,
    user: Any,
    parent_id: int | None = None,
) -> DocumentComment:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    body_text = str(body or "").strip()
    if not body_text:
        raise HTTPException(status_code=400, detail="Comment body is required")
    parent = None
    if parent_id:
        parent = (
            db.query(DocumentComment)
            .filter(
                DocumentComment.id == int(parent_id),
                DocumentComment.document_id == int(document_id),
            )
            .first()
        )
        if not parent:
            raise HTTPException(status_code=404, detail="Parent comment not found")
    row = DocumentComment(
        document_id=int(document_id),
        parent_id=int(parent_id) if parent else None,
        author_id=getattr(user, "id", None),
        author_name=getattr(user, "full_name", None) or getattr(user, "email", None),
        author_email=getattr(user, "email", None),
        body=body_text,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    log_document_activity(
        db,
        int(document_id),
        "comment_added",
        user,
        detail=f"comment:{int(row.id or 0)}",
        after_data={"comment_id": int(row.id or 0), "parent_id": int(row.parent_id or 0) or None},
    )
    db.commit()
    db.refresh(row)
    return row


def update_document_comment(db: Session, document_id: int, comment_id: int, body: str, user: Any) -> DocumentComment:
    row = (
        db.query(DocumentComment)
        .filter(DocumentComment.id == int(comment_id), DocumentComment.document_id == int(document_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    if row.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted comment cannot be updated")
    body_text = str(body or "").strip()
    if not body_text:
        raise HTTPException(status_code=400, detail="Comment body is required")
    user_id = int(getattr(user, "id", 0) or 0)
    if normalize_user_role(user) != "admin" and user_id != int(row.author_id or 0):
        raise HTTPException(status_code=403, detail="Only the author can update this comment")
    before = {"body": row.body, "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None}
    row.body = body_text
    row.updated_at = datetime.utcnow()
    db.flush()
    log_document_activity(
        db,
        int(document_id),
        "comment_updated",
        user,
        detail=f"comment:{int(row.id or 0)}",
        before_data=before,
        after_data={"body": row.body},
    )
    db.commit()
    db.refresh(row)
    return row


def delete_document_comment(db: Session, document_id: int, comment_id: int, user: Any) -> DocumentComment:
    row = (
        db.query(DocumentComment)
        .filter(DocumentComment.id == int(comment_id), DocumentComment.document_id == int(document_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    user_id = int(getattr(user, "id", 0) or 0)
    if normalize_user_role(user) != "admin" and user_id != int(row.author_id or 0):
        raise HTTPException(status_code=403, detail="Only the author can delete this comment")
    row.deleted_at = datetime.utcnow()
    row.updated_at = row.deleted_at
    db.flush()
    log_document_activity(
        db,
        int(document_id),
        "comment_deleted",
        user,
        detail=f"comment:{int(row.id or 0)}",
        after_data={"comment_id": int(row.id or 0)},
    )
    db.commit()
    db.refresh(row)
    return row


def _normalize_relation_target_type(value: Any) -> str:
    raw = str(value or "document").strip().lower().replace("-", "_")
    aliases = {
        "doc": "document",
        "mdr": "document",
        "mdr_document": "document",
        "document": "document",
        "corr": "correspondence",
        "correspondence": "correspondence",
        "letter": "correspondence",
        "mail": "correspondence",
        "meeting": "meeting_minute",
        "meeting_minute": "meeting_minute",
        "meeting_minutes": "meeting_minute",
        "minute": "meeting_minute",
        "mom": "meeting_minute",
        "comm_item": "comm_item",
        "communication_item": "comm_item",
        "communication_items": "comm_item",
        "form": "comm_item",
        "forms": "comm_item",
        "form_item": "comm_item",
        "rfi": "rfi",
        "ncr": "ncr",
        "tech": "tech",
        "technical": "tech",
        "site_log": "site_log",
        "site_logs": "site_log",
        "daily_report": "site_log",
        "work_report": "site_log",
        "workshop_report": "site_log",
        "workshop_log": "site_log",
        "permit": "permit_qc",
        "pqc": "permit_qc",
        "permit_qc": "permit_qc",
        "permit_qc_permit": "permit_qc",
    }
    normalized = aliases.get(raw)
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid relation target type")
    return normalized


def _normalize_relation_code(value: Any) -> str:
    return str(value or "").strip()


def _relation_comm_item_type_filter(target_entity_type: str) -> str | None:
    mapping = {
        "rfi": "RFI",
        "ncr": "NCR",
        "tech": "TECH",
    }
    return mapping.get(str(target_entity_type or "").strip().lower())


def _resolve_target_document(
    db: Session,
    *,
    target_document_id: int | None,
    target_code: str | None,
) -> MdrDocument | None:
    if int(target_document_id or 0) > 0:
        return db.query(MdrDocument).filter(MdrDocument.id == int(target_document_id or 0)).first()
    code = _normalize_relation_code(target_code)
    if not code:
        return None
    if code.isdigit():
        row = db.query(MdrDocument).filter(MdrDocument.id == int(code)).first()
        if row:
            return row
    return (
        db.query(MdrDocument)
        .filter(func.lower(MdrDocument.doc_number) == code.lower())
        .first()
    )


def _resolve_external_relation_target(
    db: Session,
    *,
    target_entity_type: str,
    target_entity_id: int | None,
    target_code: str | None,
) -> dict[str, Any]:
    code = _normalize_relation_code(target_code)
    entity_id = int(target_entity_id or 0)

    if target_entity_type == "correspondence":
        query = db.query(Correspondence)
        if entity_id > 0:
            row = query.filter(Correspondence.id == entity_id).first()
        elif code:
            row = query.filter(func.lower(Correspondence.reference_no) == code.lower()).first()
        else:
            row = None
        if not row:
            raise HTTPException(status_code=404, detail="Target correspondence not found")
        return {
            "entity_type": "correspondence",
            "entity_id": int(row.id or 0),
            "code": str(row.reference_no or "").strip() or f"CORR-{int(row.id or 0)}",
            "title": str(row.subject or "").strip() or None,
            "project_code": row.project_code,
            "discipline_code": row.discipline_code,
            "status": row.status,
        }

    if target_entity_type == "meeting_minute":
        query = db.query(MeetingMinute).filter(MeetingMinute.deleted_at.is_(None))
        if entity_id > 0:
            row = query.filter(MeetingMinute.id == entity_id).first()
        elif code:
            row = query.filter(func.lower(MeetingMinute.meeting_no) == code.lower()).first()
        else:
            row = None
        if not row:
            raise HTTPException(status_code=404, detail="Target meeting minute not found")
        return {
            "entity_type": "meeting_minute",
            "entity_id": int(row.id or 0),
            "code": str(row.meeting_no or "").strip() or f"MOM-{int(row.id or 0)}",
            "title": str(row.title or "").strip() or None,
            "project_code": row.project_code,
            "discipline_code": None,
            "status": row.status,
        }

    if target_entity_type in {"comm_item", "rfi", "ncr", "tech"}:
        item_type_filter = _relation_comm_item_type_filter(target_entity_type)
        query = db.query(CommItem)
        if item_type_filter:
            query = query.filter(func.upper(CommItem.item_type) == item_type_filter)
        if entity_id > 0:
            row = query.filter(CommItem.id == entity_id).first()
        elif code:
            row = query.filter(func.lower(CommItem.item_no) == code.lower()).first()
        else:
            row = None
        if not row:
            raise HTTPException(status_code=404, detail="Target form item not found")
        resolved_type = str(row.item_type or "").strip().lower()
        if resolved_type not in {"rfi", "ncr", "tech"}:
            resolved_type = "comm_item"
        return {
            "entity_type": resolved_type,
            "entity_id": int(row.id or 0),
            "code": str(row.item_no or "").strip() or f"ITEM-{int(row.id or 0)}",
            "title": str(row.title or "").strip() or None,
            "project_code": row.project_code,
            "discipline_code": row.discipline_code,
            "status": row.status_code,
        }

    if target_entity_type == "site_log":
        query = db.query(SiteLog)
        if entity_id > 0:
            row = query.filter(SiteLog.id == entity_id).first()
        elif code:
            row = query.filter(func.lower(SiteLog.log_no) == code.lower()).first()
        else:
            row = None
        if not row:
            raise HTTPException(status_code=404, detail="Target site log not found")
        return {
            "entity_type": "site_log",
            "entity_id": int(row.id or 0),
            "code": str(row.log_no or "").strip() or f"SLOG-{int(row.id or 0)}",
            "title": str(row.current_work_summary or row.summary or "").strip() or None,
            "project_code": row.project_code,
            "discipline_code": row.discipline_code,
            "status": row.status_code,
        }

    if target_entity_type == "permit_qc":
        query = db.query(PermitQcPermit)
        if entity_id > 0:
            row = query.filter(PermitQcPermit.id == entity_id).first()
        elif code:
            row = query.filter(func.lower(PermitQcPermit.permit_no) == code.lower()).first()
        else:
            row = None
        if not row:
            raise HTTPException(status_code=404, detail="Target permit QC not found")
        return {
            "entity_type": "permit_qc",
            "entity_id": int(row.id or 0),
            "code": str(row.permit_no or "").strip() or f"PQC-{int(row.id or 0)}",
            "title": str(row.title or "").strip() or None,
            "project_code": row.project_code,
            "discipline_code": row.discipline_code,
            "status": row.status_code,
        }

    raise HTTPException(status_code=400, detail="Invalid relation target type")


def list_document_relations(db: Session, document_id: int, user: Any) -> dict[str, list[Any]]:
    document = (
        db.query(MdrDocument)
        .options(
            joinedload(MdrDocument.outgoing_relations).joinedload(DocumentRelation.target_document),
            joinedload(MdrDocument.incoming_relations).joinedload(DocumentRelation.source_document),
        )
        .filter(MdrDocument.id == int(document_id))
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    external_rows = (
        db.query(DocumentExternalRelation)
        .filter(DocumentExternalRelation.source_document_id == int(document_id))
        .order_by(DocumentExternalRelation.created_at.desc(), DocumentExternalRelation.id.desc())
        .all()
    )
    return {
        "outgoing": [
            row for row in document.outgoing_relations or [] if getattr(row.target_document, "deleted_at", None) is None
        ] + external_rows,
        "incoming": [
            row for row in document.incoming_relations or [] if getattr(row.source_document, "deleted_at", None) is None
        ],
    }


def create_document_relation(
    db: Session,
    document_id: int,
    target_document_id: int | None,
    relation_type: str,
    notes: str | None,
    user: Any,
    *,
    target_entity_type: str = "document",
    target_entity_id: int | None = None,
    target_code: str | None = None,
) -> DocumentRelation | DocumentExternalRelation:
    source_document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not source_document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=source_document.project_code,
        discipline_code=source_document.discipline_code,
    )
    if source_document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")

    normalized_target_type = _normalize_relation_target_type(target_entity_type)
    normalized_type = str(relation_type or "").strip().lower() or "related"

    if normalized_target_type != "document":
        target = _resolve_external_relation_target(
            db,
            target_entity_type=normalized_target_type,
            target_entity_id=target_entity_id,
            target_code=target_code,
        )
        enforce_scope_access(
            db,
            user,
            project_code=target.get("project_code"),
            discipline_code=target.get("discipline_code"),
        )
        stored_target_type = str(target.get("entity_type") or normalized_target_type).strip().lower()
        existing_external = (
            db.query(DocumentExternalRelation)
            .filter(
                DocumentExternalRelation.source_document_id == int(document_id),
                DocumentExternalRelation.target_entity_type == stored_target_type,
                DocumentExternalRelation.target_entity_id == int(target["entity_id"]),
                DocumentExternalRelation.relation_type == normalized_type,
            )
            .first()
        )
        if existing_external:
            raise HTTPException(status_code=409, detail="Relation already exists")
        row = DocumentExternalRelation(
            source_document_id=int(document_id),
            target_entity_type=stored_target_type,
            target_entity_id=int(target["entity_id"]),
            target_code=str(target["code"]),
            target_title=target.get("title"),
            target_project_code=target.get("project_code"),
            target_status=target.get("status"),
            relation_type=normalized_type,
            notes=str(notes or "").strip() or None,
            created_by_id=getattr(user, "id", None),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        log_document_activity(
            db,
            int(document_id),
            "relation_added",
            user,
            detail=f"external_relation:{stored_target_type}:{int(row.id or 0)}",
            after_data={
                "target_entity_type": stored_target_type,
                "target_entity_id": int(target["entity_id"]),
                "target_code": str(target["code"]),
                "relation_type": normalized_type,
            },
        )
        db.commit()
        db.refresh(row)
        return row

    target_document = _resolve_target_document(
        db,
        target_document_id=target_document_id,
        target_code=target_code,
    )
    if not target_document or target_document.deleted_at:
        raise HTTPException(status_code=404, detail="Target document not found")
    enforce_scope_access(
        db,
        user,
        project_code=target_document.project_code,
        discipline_code=target_document.discipline_code,
    )
    if int(document_id) == int(target_document.id or 0):
        raise HTTPException(status_code=400, detail="Cannot relate a document to itself")
    existing = (
        db.query(DocumentRelation)
        .filter(
            DocumentRelation.source_document_id == int(document_id),
            DocumentRelation.target_document_id == int(target_document.id or 0),
            DocumentRelation.relation_type == normalized_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Relation already exists")
    row = DocumentRelation(
        source_document_id=int(document_id),
        target_document_id=int(target_document.id or 0),
        relation_type=normalized_type,
        notes=str(notes or "").strip() or None,
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    log_document_activity(
        db,
        int(document_id),
        "relation_added",
        user,
        detail=f"relation:{int(row.id or 0)}",
        after_data={"target_document_id": int(target_document.id or 0), "relation_type": normalized_type},
    )
    db.commit()
    db.refresh(row)
    return row


def delete_document_relation(db: Session, document_id: int, relation_id: int | str, user: Any) -> None:
    relation_key = str(relation_id or "").strip()
    is_external = relation_key.lower().startswith("external:")
    if is_external:
        try:
            external_id = int(relation_key.split(":", 1)[1])
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Relation not found") from exc
        external_row = (
            db.query(DocumentExternalRelation)
            .filter(
                DocumentExternalRelation.id == external_id,
                DocumentExternalRelation.source_document_id == int(document_id),
            )
            .first()
        )
        if not external_row:
            raise HTTPException(status_code=404, detail="Relation not found")
        source_document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
        if not source_document:
            raise HTTPException(status_code=404, detail="Document not found")
        enforce_scope_access(
            db,
            user,
            project_code=source_document.project_code,
            discipline_code=source_document.discipline_code,
        )
        if source_document.deleted_at:
            raise HTTPException(status_code=409, detail="Deleted document is read-only")
        db.delete(external_row)
        log_document_activity(
            db,
            int(document_id),
            "relation_removed",
            user,
            detail=f"external_relation:{external_id}",
        )
        db.commit()
        return

    try:
        numeric_relation_id = int(relation_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Relation not found") from exc
    row = (
        db.query(DocumentRelation)
        .filter(DocumentRelation.id == numeric_relation_id, DocumentRelation.source_document_id == int(document_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Relation not found")
    source_document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not source_document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=source_document.project_code,
        discipline_code=source_document.discipline_code,
    )
    if source_document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    db.delete(row)
    log_document_activity(
        db,
        int(document_id),
        "relation_removed",
        user,
        detail=f"relation:{numeric_relation_id}",
    )
    db.commit()


def list_tags(db: Session) -> list[DocumentTag]:
    return db.query(DocumentTag).order_by(DocumentTag.name.asc(), DocumentTag.id.asc()).all()


def create_tag(db: Session, name: str, color: str | None, user: Any) -> DocumentTag:
    normalized_name = _normalize_tag_name(name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Tag name is required")
    for row in db.query(DocumentTag).order_by(DocumentTag.id.asc()).all():
        if _normalize_tag_name(row.name).lower() == normalized_name.lower():
            return row
    row = DocumentTag(name=normalized_name, color=str(color or "").strip() or None, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_document_tags(db: Session, document_id: int, user: Any) -> list[DocumentTagAssignment]:
    document = (
        db.query(MdrDocument)
        .options(joinedload(MdrDocument.tag_assignments).joinedload(DocumentTagAssignment.tag))
        .filter(MdrDocument.id == int(document_id))
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    return list(document.tag_assignments or [])


def assign_tag_to_document(
    db: Session,
    document_id: int,
    tag_name: str | None,
    tag_id: int | None,
    color: str | None,
    user: Any,
) -> DocumentTagAssignment:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    target_tag: DocumentTag | None = None
    if tag_id:
        target_tag = db.query(DocumentTag).filter(DocumentTag.id == int(tag_id)).first()
    if not target_tag:
        target_tag = create_tag(db, str(tag_name or ""), color, user)
    existing = (
        db.query(DocumentTagAssignment)
        .filter(
            DocumentTagAssignment.document_id == int(document_id),
            DocumentTagAssignment.tag_id == int(target_tag.id or 0),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Tag already assigned")
    row = DocumentTagAssignment(
        document_id=int(document_id),
        tag_id=int(target_tag.id or 0),
        assigned_by_id=getattr(user, "id", None),
        assigned_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    log_document_activity(
        db,
        int(document_id),
        "tag_added",
        user,
        detail=f"tag:{int(target_tag.id or 0)}",
        after_data={"tag_id": int(target_tag.id or 0), "tag_name": target_tag.name},
    )
    db.commit()
    db.refresh(row)
    return row


def remove_tag_from_document(db: Session, document_id: int, tag_id: int, user: Any) -> None:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    row = (
        db.query(DocumentTagAssignment)
        .filter(
            DocumentTagAssignment.document_id == int(document_id),
            DocumentTagAssignment.tag_id == int(tag_id),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Tag assignment not found")
    db.delete(row)
    log_document_activity(
        db,
        int(document_id),
        "tag_removed",
        user,
        detail=f"tag:{int(tag_id)}",
    )
    db.commit()
# ---------------------------------------------------------
# 4. Main Upload Logic
# ---------------------------------------------------------
def save_upload_file(
    db: Session,
    file: UploadFile,
    document_id: int,
    revision_code: str,
    status_code: str = "Uploaded",
    file_kind: str = "pdf",
    is_primary: bool = True,
    companion_file_id: int | None = None,
    openproject_work_package_id: int | None = None,
    commit: bool = True,
    is_admin: bool = False,
    actor: Any | None = None,
    log_revision: bool = True,
    touch_revision: bool = True,
    update_revision_pointer: bool = True,
) -> ArchiveFile:
    del is_admin
    storage = StorageManager(db)

    doc = db.query(MdrDocument).filter(MdrDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    rev = db.query(DocumentRevision).filter(
        DocumentRevision.document_id == document_id,
        DocumentRevision.revision == revision_code,
    ).first()
    if rev:
        rev.status = status_code
        if touch_revision:
            rev.created_at = datetime.utcnow()
    else:
        rev = DocumentRevision(
            document_id=document_id,
            revision=revision_code,
            status=status_code,
            notes="Created via Upload",
        )
        db.add(rev)
        db.flush()

    normalized_kind = _normalize_archive_file_kind(file_kind)

    proj_name = doc.project.name_e if doc.project else doc.project_code
    mdr_folder = folder_service.get_mdr_folder_name(db, doc.mdr_code)

    phase_name = doc.phase_code
    if doc.phase:
        phase_name = doc.phase.name_e or doc.phase_code

    disc_name = "General"
    disc_code = doc.discipline_code or "GN"
    if doc.discipline:
        disc_name = doc.discipline.name_e

    pkg_name = "General"
    pkg_code = doc.package_code or "00"
    if doc.package:
        pkg_name = doc.package.name_e or doc.package.name_p or doc.package_code

    _, file_extension = os.path.splitext(file.filename)
    storage, clean_name, target_path = _archive_storage_target(
        db,
        doc,
        revision_code=revision_code,
        extension=file_extension,
        file_kind=normalized_kind,
    )

    # Check if WebDAV mode
    if target_path.startswith("webdav://"):
        saved = storage.save_upload_to_webdav(
            file=file,
            remote_relative_path=_webdav_relative_path(target_path),
            file_kind=normalized_kind,
        )
    else:
        # Mount/local mode: use existing logic
        target_folder = storage.get_mdr_path(
            project_code=doc.project_code,
            project_name=proj_name,
            mdr_folder_name=mdr_folder,
            phase_name=phase_name,
            phase_code=doc.phase_code or phase_name,
            disc_name=disc_name,
            disc_code=disc_code,
            pkg_name=pkg_name,
            pkg_code=pkg_code,
            package_name=pkg_name,
            file_kind=normalized_kind,
        )
        saved = storage.save_upload_secure(
            file=file,
            destination_folder=target_folder,
            new_name=clean_name,
            file_kind=normalized_kind,
        )

    if update_revision_pointer:
        rev.file_path = saved.stored_path
        rev.file_name = clean_name

    integrations = get_storage_integrations(db)
    mirror_plan = resolve_mirror_enqueue_plan(integrations)
    mirror_provider = str(mirror_plan.get("provider") or "")
    mirror_status = str(mirror_plan.get("status") or "disabled")

    archive_entry = ArchiveFile(
        revision_id=rev.id,
        original_name=clean_name,
        stored_path=saved.stored_path,
        mime_type=saved.declared_mime or file.content_type,
        detected_mime=saved.detected_mime,
        validation_status=saved.validation_status,
        sha256=saved.sha256,
        size_bytes=saved.size_bytes,
        storage_backend="nextcloud" if saved.stored_path.startswith("webdav://") else storage.resolve_storage_backend_for_path(saved.stored_path),
        gdrive_file_id=None,
        mirror_provider=mirror_provider or None,
        mirror_remote_id=None,
        mirror_remote_url=None,
        mirror_status=mirror_status,
        mirror_updated_at=datetime.utcnow(),
        file_kind=normalized_kind,
        is_primary=bool(is_primary),
        companion_file_id=companion_file_id,
        revision=revision_code,
        status=status_code,
        uploaded_by=getattr(actor, "email", None) or "User",
        uploaded_at=datetime.utcnow(),
    )

    db.add(archive_entry)
    db.flush()
    if log_revision:
        log_document_activity(
            db,
            int(document_id),
            "revision_uploaded",
            actor,
            detail=f"revision:{revision_code}",
            after_data={
                "revision": revision_code,
                "file_id": int(archive_entry.id or 0),
                "file_kind": normalized_kind,
                "status": status_code,
            },
        )
    if bool(mirror_plan.get("enqueue")):
        enqueue_archive_mirror_job(
            db,
            archive_file_id=archive_entry.id,
            work_package_id=openproject_work_package_id,
        )

    if commit:
        db.commit()
        db.refresh(archive_entry)

    return archive_entry


def add_revision_file(
    db: Session,
    revision_id: int,
    file: UploadFile,
    user: Any,
    *,
    file_kind: str = "pdf",
    status_code: str | None = None,
) -> ArchiveFile:
    revision = (
        db.query(DocumentRevision)
        .options(
            joinedload(DocumentRevision.document),
            joinedload(DocumentRevision.archive_files),
        )
        .filter(DocumentRevision.id == int(revision_id))
        .first()
    )
    if not revision or not revision.document:
        raise HTTPException(status_code=404, detail="Revision not found")
    document = revision.document
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )

    normalized_kind = _normalize_archive_file_kind(file_kind)
    live_files = [row for row in (revision.archive_files or []) if row.deleted_at is None]
    same_kind = [row for row in live_files if _normalize_archive_file_kind(row.file_kind) == normalized_kind]
    if same_kind:
        label = "Native" if normalized_kind == "native" else "PDF/خروجی"
        raise HTTPException(status_code=409, detail=f"برای این Revision فایل {label} از قبل ثبت شده است.")

    companion_kind = "pdf" if normalized_kind == "native" else "native"
    companion = next((row for row in live_files if _normalize_archive_file_kind(row.file_kind) == companion_kind), None)
    new_file: ArchiveFile | None = None
    try:
        new_file = save_upload_file(
            db=db,
            file=file,
            document_id=int(document.id or 0),
            revision_code=str(revision.revision or "00").strip() or "00",
            status_code=str(status_code or revision.status or "IFA").strip() or "IFA",
            file_kind=normalized_kind,
            is_primary=normalized_kind == "pdf",
            companion_file_id=int(companion.id or 0) if companion else None,
            commit=False,
            actor=user,
            log_revision=False,
            touch_revision=False,
            update_revision_pointer=normalized_kind == "pdf",
        )
        if companion:
            companion.companion_file_id = int(new_file.id or 0)
        if normalized_kind == "pdf":
            revision.file_path = new_file.stored_path
            revision.file_name = new_file.original_name
        if status_code:
            revision.status = str(status_code).strip() or revision.status
        log_document_activity(
            db,
            int(document.id or 0),
            "revision_file_added",
            user,
            detail=f"revision:{revision.revision}",
            after_data={
                "revision_id": int(revision.id or 0),
                "revision": revision.revision,
                "file_id": int(new_file.id or 0),
                "file_kind": normalized_kind,
                "status": new_file.status,
                "companion_file_id": int(companion.id or 0) if companion else None,
            },
        )
        db.commit()
        db.refresh(new_file)
        return new_file
    except Exception:
        db.rollback()
        if new_file is not None:
            try:
                _delete_physical_file(db, new_file.stored_path)
            except Exception:
                pass
        raise


def save_dual_upload_files(
    db: Session,
    *,
    pdf_file: UploadFile,
    native_file: UploadFile,
    document_id: int,
    revision_code: str,
    status_code: str = "Uploaded",
    openproject_work_package_id: int | None = None,
    is_admin: bool = False,
    actor: Any | None = None,
) -> tuple[ArchiveFile, ArchiveFile]:
    """
    Save PDF + Native files on the same revision and cross-link them as companions.
    """
    pdf_entry: ArchiveFile | None = None
    native_entry: ArchiveFile | None = None
    saved_paths: list[str] = []
    try:
        pdf_entry = save_upload_file(
            db=db,
            file=pdf_file,
            document_id=document_id,
            revision_code=revision_code,
            status_code=status_code,
            file_kind="pdf",
            is_primary=True,
            openproject_work_package_id=openproject_work_package_id,
            commit=False,
            is_admin=is_admin,
            actor=actor,
            log_revision=False,
        )
        saved_paths.append(pdf_entry.stored_path)

        native_entry = save_upload_file(
            db=db,
            file=native_file,
            document_id=document_id,
            revision_code=revision_code,
            status_code=status_code,
            file_kind="native",
            is_primary=False,
            openproject_work_package_id=openproject_work_package_id,
            commit=False,
            is_admin=is_admin,
            actor=actor,
            log_revision=False,
        )
        saved_paths.append(native_entry.stored_path)

        pdf_entry.companion_file_id = native_entry.id
        native_entry.companion_file_id = pdf_entry.id

        # Keep revision file pointer on the primary (PDF) file.
        revision_row = db.query(DocumentRevision).filter(DocumentRevision.id == pdf_entry.revision_id).first()
        if revision_row:
            revision_row.file_path = pdf_entry.stored_path
            revision_row.file_name = pdf_entry.original_name

        db.commit()
        db.refresh(pdf_entry)
        db.refresh(native_entry)
        log_document_activity(
            db,
            int(document_id),
            "revision_uploaded",
            actor,
            detail=f"revision:{revision_code}",
            after_data={
                "revision": revision_code,
                "pdf_file_id": int(pdf_entry.id or 0),
                "native_file_id": int(native_entry.id or 0),
                "status": status_code,
            },
        )
        db.commit()
        db.refresh(pdf_entry)
        db.refresh(native_entry)
        return pdf_entry, native_entry
    except Exception:
        db.rollback()
        for path in saved_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        raise
# ---------------------------------------------------------
# 5. Full Register & Upload (New Feature)
# ---------------------------------------------------------
def register_and_upload_document(
    db: Session,
    file: UploadFile,
    meta_data: dict, 
    revision_code: str,
    status_code: str,
    file_kind: str = "pdf",
    openproject_work_package_id: int | None = None,
    is_admin: bool = False,
    actor: Any | None = None,
) -> ArchiveFile:
    """
    ثبت کامل مدرک (Master) و آپلود فایل در یک مرحله.
    """
    
    subject_e, subject_p = _subject_pair_for_titles(
        meta_data.get("subject_e"),
        meta_data.get("subject_p"),
    )

    # 1. ابتدا سند را در جدول MDR ثبت می‌کنیم
    existing = db.query(MdrDocument).filter(MdrDocument.doc_number == meta_data['doc_number']).first()
    created_new_document = False
    if not existing and not (subject_e or subject_p):
        subjectless_existing = _scope_subjectless_existing_from_meta(db, meta_data)
        if subjectless_existing:
            doc = subjectless_existing
            db.flush()
            archive_entry = save_upload_file(
                db=db,
                file=file,
                document_id=doc.id,
                revision_code=revision_code,
                status_code=status_code,
                file_kind=file_kind,
                openproject_work_package_id=openproject_work_package_id,
                is_admin=is_admin,
                actor=actor,
            )
            return archive_entry

        normalized_doc_number = str(meta_data.get("doc_number") or "").strip().upper()
        expected_doc_number = _subjectless_expected_doc_number_from_meta(db, meta_data)
        if normalized_doc_number != expected_doc_number:
            raise HTTPException(
                status_code=422,
                detail=f"برای مدرک بدون Subject سریال باید از 01 شروع شود. کد صحیح: {expected_doc_number}",
            )
    
    if existing:
        # اگر کد وجود دارد، از همان استفاده کن
        doc = existing
        # اختیاری: می‌توانیم عنوان‌ها را آپدیت کنیم
        _refresh_doc_titles_from_subjects(
            doc,
            db,
            subject_e,
            subject_p,
        )
    else:
        # ساخت سند جدید
        meta_data["mdr_code"] = _active_mdr_code_or_422(db, meta_data.get("mdr_code"))
        doc = mdr_service.create_mdr_document(
            db,
            doc_number=meta_data['doc_number'],
            project_code=meta_data['project_code'],
            mdr_code=meta_data['mdr_code'],
            phase_code=meta_data['phase'],
            discipline_code=meta_data['discipline'],
            package_code=meta_data['package'],
            block=meta_data['block'],
            level_code=meta_data['level'],
            title_e=subject_e,
            title_p=subject_p,
            subject=_subject_storage(subject_e, subject_p)
        )
        created_new_document = True
    
    db.flush() # برای گرفتن ID سند
    if created_new_document:
        log_document_activity(
            db,
            int(doc.id or 0),
            "created",
            actor,
            after_data=serialize_document_snapshot(doc),
        )

    # 2. آپلود فایل
    archive_entry = save_upload_file(
        db=db,
        file=file,
        document_id=doc.id,
        revision_code=revision_code,
        status_code=status_code,
        file_kind=file_kind,
        openproject_work_package_id=openproject_work_package_id,
        is_admin=is_admin,
        actor=actor,
    )
    
    return archive_entry


def register_document_metadata(
    db: Session,
    *,
    meta_data: dict,
    actor: Any | None = None,
) -> tuple[MdrDocument, bool]:
    """
    Register only MDR document metadata (no archive upload).
    Returns: (document, created_flag)
    """
    doc_number = str(meta_data.get("doc_number") or "").strip().upper()
    if not doc_number:
        raise HTTPException(status_code=400, detail="Document number is required.")

    existing = db.query(MdrDocument).filter(MdrDocument.doc_number == doc_number).first()
    if existing:
        return existing, False

    subject_e, subject_p = _subject_pair_for_titles(
        meta_data.get("subject_e"),
        meta_data.get("subject_p"),
    )
    if not (subject_e or subject_p):
        subjectless_existing = _scope_subjectless_existing_from_meta(db, meta_data)
        if subjectless_existing:
            return subjectless_existing, False
        expected_doc_number = _subjectless_expected_doc_number_from_meta(db, meta_data)
        if doc_number != expected_doc_number:
            raise HTTPException(
                status_code=422,
                detail=f"برای مدرک بدون Subject سریال باید از 01 شروع شود. کد صحیح: {expected_doc_number}",
            )

    active_mdr_code = _active_mdr_code_or_422(db, meta_data.get("mdr_code"))
    doc = mdr_service.create_mdr_document(
        db,
        doc_number=doc_number,
        project_code=str(meta_data.get("project_code") or "").strip().upper(),
        mdr_code=active_mdr_code,
        phase_code=str(meta_data.get("phase") or "X").strip().upper() or "X",
        discipline_code=str(meta_data.get("discipline") or "XX").strip().upper() or "XX",
        package_code=str(meta_data.get("package") or "").strip().upper(),
        block=str(meta_data.get("block") or "").strip().upper(),
        level_code=str(meta_data.get("level") or "GEN").strip().upper() or "GEN",
        title_e=subject_e,
        title_p=subject_p,
        subject=_subject_storage(subject_e, subject_p),
    )
    db.commit()
    db.refresh(doc)
    log_document_activity(
        db,
        int(doc.id or 0),
        "created",
        actor,
        after_data=serialize_document_snapshot(doc),
    )
    db.commit()
    db.refresh(doc)
    return doc, True


def register_and_upload_dual_document(
    db: Session,
    *,
    pdf_file: UploadFile,
    native_file: UploadFile,
    meta_data: dict,
    revision_code: str,
    status_code: str,
    openproject_work_package_id: int | None = None,
    is_admin: bool = False,
    actor: Any | None = None,
) -> tuple[ArchiveFile, ArchiveFile]:
    """
    Register document metadata (if needed) and upload PDF + Native together.
    """
    subject_e, subject_p = _subject_pair_for_titles(
        meta_data.get("subject_e"),
        meta_data.get("subject_p"),
    )

    existing = db.query(MdrDocument).filter(MdrDocument.doc_number == meta_data["doc_number"]).first()
    created_new_document = False
    if not existing and not (subject_e or subject_p):
        subjectless_existing = _scope_subjectless_existing_from_meta(db, meta_data)
        if subjectless_existing:
            doc = subjectless_existing
            db.flush()
            return save_dual_upload_files(
                db=db,
                pdf_file=pdf_file,
                native_file=native_file,
                document_id=doc.id,
                revision_code=revision_code,
                status_code=status_code,
                openproject_work_package_id=openproject_work_package_id,
                is_admin=is_admin,
                actor=actor,
            )
        normalized_doc_number = str(meta_data.get("doc_number") or "").strip().upper()
        expected_doc_number = _subjectless_expected_doc_number_from_meta(db, meta_data)
        if normalized_doc_number != expected_doc_number:
            raise HTTPException(
                status_code=422,
                detail=f"برای مدرک بدون Subject سریال باید از 01 شروع شود. کد صحیح: {expected_doc_number}",
            )

    if existing:
        doc = existing
        _refresh_doc_titles_from_subjects(
            doc,
            db,
            subject_e,
            subject_p,
        )
    else:
        meta_data["mdr_code"] = _active_mdr_code_or_422(db, meta_data.get("mdr_code"))
        doc = mdr_service.create_mdr_document(
            db,
            doc_number=meta_data["doc_number"],
            project_code=meta_data["project_code"],
            mdr_code=meta_data["mdr_code"],
            phase_code=meta_data["phase"],
            discipline_code=meta_data["discipline"],
            package_code=meta_data["package"],
            block=meta_data["block"],
            level_code=meta_data["level"],
            title_e=subject_e,
            title_p=subject_p,
            subject=_subject_storage(subject_e, subject_p),
        )
        created_new_document = True

    db.flush()
    if created_new_document:
        log_document_activity(
            db,
            int(doc.id or 0),
            "created",
            actor,
            after_data=serialize_document_snapshot(doc),
        )

    return save_dual_upload_files(
        db=db,
        pdf_file=pdf_file,
        native_file=native_file,
        document_id=doc.id,
        revision_code=revision_code,
        status_code=status_code,
        openproject_work_package_id=openproject_work_package_id,
        is_admin=is_admin,
        actor=actor,
    )
