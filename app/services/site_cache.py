from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import secrets
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    ArchiveFile,
    DocumentRevision,
    LocalSyncManifest,
    MdrDocument,
    SiteCacheAgentToken,
    SiteCachePinRule,
    SiteCacheProfile,
    SiteCacheProfileCIDR,
)

ENTITY_ARCHIVE_FILE = "archive_file"
SITE_SCOPE_PREFIX = "site:"
DEFAULT_SITE_RULE_STATUSES = "IFA,IFC"
DEFAULT_FALLBACK_MODE = "local_first"
ALLOWED_FALLBACK_MODES = {"local_first", "hq_first"}
AGENT_TOKEN_PREFIX = "sca_"


_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def normalize_site_code(value: str | None) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    return re.sub(r"[^A-Z0-9_-]", "", raw)


def normalize_fallback_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    if mode in ALLOWED_FALLBACK_MODES:
        return mode
    return DEFAULT_FALLBACK_MODE


def normalize_csv_codes(value: str | Iterable[str] | None, *, uppercase: bool = True) -> str:
    raw_items: list[str] = []
    if value is None:
        raw_items = []
    elif isinstance(value, str):
        raw_items = [part.strip() for part in value.split(",")]
    else:
        raw_items = [str(part or "").strip() for part in value]

    out: list[str] = []
    for item in raw_items:
        if not item:
            continue
        cleaned = item.upper() if uppercase else item
        if cleaned not in out:
            out.append(cleaned)
    return ",".join(out)


def parse_csv_codes(value: str | None, *, uppercase: bool = True) -> list[str]:
    return normalize_csv_codes(value or "", uppercase=uppercase).split(",") if str(value or "").strip() else []


def normalize_cidr(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    network = ipaddress.ip_network(raw, strict=False)
    return str(network)


def site_scope_value(site_code: str) -> str:
    normalized = normalize_site_code(site_code)
    return f"{SITE_SCOPE_PREFIX}{normalized}" if normalized else SITE_SCOPE_PREFIX.rstrip(":")


def site_manifest_policy_scope(site_code: str) -> str:
    return f"{ENTITY_ARCHIVE_FILE}:{site_scope_value(site_code)}"


def hash_agent_token(token: str) -> str:
    value = str(token or "").strip()
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def mint_agent_token_value() -> str:
    return f"{AGENT_TOKEN_PREFIX}{secrets.token_urlsafe(40)}"


def agent_token_hint(token: str) -> str:
    value = str(token or "").strip()
    if len(value) <= 10:
        return value
    return f"{value[:6]}...{value[-4:]}"


def _safe_segment(value: str | None, default: str = "-") -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    cleaned = _SAFE_SEGMENT_RE.sub("-", raw).strip("-")
    return cleaned or default


def _sha256_for_path(path_value: str | None) -> str:
    path = str(path_value or "").strip()
    if not path or not os.path.exists(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_archive_relative_path(file_row: ArchiveFile) -> str:
    revision = file_row.document_revision
    document = revision.document if revision else None
    project_code = _safe_segment(document.project_code if document else "", default="project")
    project = getattr(document, "project", None) if document else None
    project_name = _safe_segment(
        getattr(project, "name_e", None) or getattr(project, "name_p", None) or "",
        default="",
    )
    project_folder = f"{project_code} - {project_name}" if project_name and project_name.lower() != "unk" else project_code
    category = getattr(document, "mdr_category", None) if document else None
    mdr_folder = _safe_segment(
        getattr(category, "folder_name", None)
        or getattr(category, "name_e", None)
        or (document.mdr_code if document else ""),
        default="MDR",
    )
    phase_code = _safe_segment(document.phase_code if document else "", default="Phase")
    discipline_code = _safe_segment(document.discipline_code if document else "", default="GN")
    package = getattr(document, "package", None) if document else None
    package_name = _safe_segment(
        getattr(package, "name_e", None)
        or getattr(package, "name_p", None)
        or (document.package_code if document else ""),
        default="00",
    )
    kind = _safe_segment(file_row.file_kind or "pdf", default="pdf")
    file_name = _safe_segment(file_row.original_name or f"file-{file_row.id}", default=f"file-{file_row.id}")
    return "/".join([project_folder, mdr_folder, phase_code, discipline_code, package_name, kind, file_name])


def _effective_version_hash(file_row: ArchiveFile, manifest_row: LocalSyncManifest | None = None) -> str:
    if manifest_row and str(manifest_row.version_hash or "").strip():
        return str(manifest_row.version_hash).strip().lower()
    if str(file_row.sha256 or "").strip():
        return str(file_row.sha256).strip().lower()
    return _sha256_for_path(file_row.stored_path).lower()


def _base_archive_query(db: Session):
    return (
        db.query(ArchiveFile)
        .join(DocumentRevision, ArchiveFile.revision_id == DocumentRevision.id)
        .join(MdrDocument, DocumentRevision.document_id == MdrDocument.id)
        .filter(ArchiveFile.deleted_at.is_(None), MdrDocument.deleted_at.is_(None))
    )


def _apply_rule_filters(query, profile: SiteCacheProfile, rule: SiteCachePinRule):
    project_code = str(rule.project_code or profile.project_code or "").strip().upper()
    if project_code:
        query = query.filter(MdrDocument.project_code == project_code)

    discipline_code = str(rule.discipline_code or "").strip().upper()
    if discipline_code:
        query = query.filter(MdrDocument.discipline_code == discipline_code)

    package_code = str(rule.package_code or "").strip().upper()
    if package_code:
        query = query.filter(MdrDocument.package_code == package_code)

    statuses = parse_csv_codes(rule.status_codes or DEFAULT_SITE_RULE_STATUSES, uppercase=True)
    if statuses:
        query = query.filter(func.upper(func.coalesce(ArchiveFile.status, "")).in_(statuses))

    if rule.primary_only:
        query = query.filter(or_(ArchiveFile.is_primary.is_(True), ArchiveFile.is_primary.is_(None)))
    if not rule.include_native:
        query = query.filter(or_(ArchiveFile.file_kind.is_(None), ArchiveFile.file_kind != "native"))

    # Site cache always syncs latest revision to keep local nodes lean and deterministic.
    latest_revision_subquery = (
        query.session.query(
            DocumentRevision.document_id.label("document_id"),
            func.max(DocumentRevision.id).label("latest_revision_id"),
        )
        .group_by(DocumentRevision.document_id)
        .subquery()
    )
    query = query.join(
        latest_revision_subquery,
        and_(
            DocumentRevision.document_id == latest_revision_subquery.c.document_id,
            DocumentRevision.id == latest_revision_subquery.c.latest_revision_id,
        ),
    )
    return query


def collect_profile_file_candidates(
    db: Session,
    profile: SiteCacheProfile,
) -> tuple[set[int], dict[int, str]]:
    rules = [row for row in (profile.pin_rules or []) if row.is_active]
    if not rules:
        return set(), {}

    selected_ids: set[int] = set()
    version_hashes: dict[int, str] = {}
    for rule in sorted(rules, key=lambda item: (item.priority, item.id)):
        query = _base_archive_query(db)
        query = _apply_rule_filters(query, profile, rule)
        rows = (
            query.options(
                joinedload(ArchiveFile.document_revision).joinedload(DocumentRevision.document),
            )
            .order_by(ArchiveFile.uploaded_at.desc(), ArchiveFile.id.desc())
            .all()
        )
        for row in rows:
            file_id = int(row.id or 0)
            if file_id <= 0:
                continue
            selected_ids.add(file_id)
            version_hashes[file_id] = _effective_version_hash(row)
    return selected_ids, version_hashes


def rebuild_profile_manifest(
    db: Session,
    profile: SiteCacheProfile,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    scope = site_manifest_policy_scope(profile.code)
    selected_ids, selected_hashes = collect_profile_file_candidates(db, profile)

    existing_rows = (
        db.query(LocalSyncManifest)
        .filter(LocalSyncManifest.policy_scope == scope)
        .all()
    )
    existing_by_file: dict[int, LocalSyncManifest] = {int(row.file_id): row for row in existing_rows}
    existing_ids = set(existing_by_file.keys())

    to_disable = sorted(existing_ids - selected_ids)
    to_enable = sorted(selected_ids)

    created = 0
    updated = 0
    disabled = 0

    if not dry_run:
        for file_id in to_enable:
            row = existing_by_file.get(file_id)
            version_hash = str(selected_hashes.get(file_id) or "").strip().lower()
            if not version_hash:
                continue
            if row is None:
                db.add(
                    LocalSyncManifest(
                        file_id=file_id,
                        version_hash=version_hash,
                        is_pinned=True,
                        policy_scope=scope,
                    )
                )
                created += 1
                continue
            changed = False
            if not row.is_pinned:
                row.is_pinned = True
                changed = True
            if str(row.version_hash or "").strip().lower() != version_hash:
                row.version_hash = version_hash
                changed = True
            if changed:
                row.last_modified_at = datetime.utcnow()
                updated += 1

        for file_id in to_disable:
            row = existing_by_file.get(file_id)
            if not row or not row.is_pinned:
                continue
            row.is_pinned = False
            row.last_modified_at = datetime.utcnow()
            disabled += 1

    return {
        "scope": scope,
        "selected_count": len(selected_ids),
        "existing_count": len(existing_ids),
        "to_enable_count": len(to_enable),
        "to_disable_count": len(to_disable),
        "created_count": created,
        "updated_count": updated,
        "disabled_count": disabled,
        "dry_run": bool(dry_run),
    }


def resolve_site_profile_by_token(
    db: Session,
    *,
    site_code: str,
    token_value: str,
) -> tuple[SiteCacheProfile | None, SiteCacheAgentToken | None]:
    normalized_code = normalize_site_code(site_code)
    token_hash = hash_agent_token(token_value)
    if not normalized_code or not token_hash:
        return None, None

    token_row = (
        db.query(SiteCacheAgentToken)
        .options(joinedload(SiteCacheAgentToken.profile))
        .filter(
            SiteCacheAgentToken.token_hash == token_hash,
            SiteCacheAgentToken.is_active.is_(True),
            SiteCacheAgentToken.revoked_at.is_(None),
        )
        .first()
    )
    if not token_row:
        return None, None

    profile = token_row.profile
    if not profile:
        return None, None
    if not profile.is_active:
        return None, None
    if normalize_site_code(profile.code) != normalized_code:
        return None, None
    return profile, token_row


def build_site_manifest(
    db: Session,
    *,
    profile: SiteCacheProfile,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    scope = site_manifest_policy_scope(profile.code)
    manifest_rows = (
        db.query(LocalSyncManifest)
        .filter(
            LocalSyncManifest.policy_scope == scope,
            LocalSyncManifest.is_pinned.is_(True),
        )
        .order_by(LocalSyncManifest.last_modified_at.desc(), LocalSyncManifest.id.desc())
        .limit(max(1, min(int(limit or 5000), 20000)))
        .all()
    )
    if not manifest_rows:
        return []

    file_ids = [int(row.file_id) for row in manifest_rows if int(row.file_id or 0) > 0]
    if not file_ids:
        return []

    archive_rows = (
        db.query(ArchiveFile)
        .join(DocumentRevision, ArchiveFile.revision_id == DocumentRevision.id)
        .join(MdrDocument, DocumentRevision.document_id == MdrDocument.id)
        .options(
            joinedload(ArchiveFile.document_revision).joinedload(DocumentRevision.document),
        )
        .filter(
            ArchiveFile.id.in_(file_ids),
            ArchiveFile.deleted_at.is_(None),
            MdrDocument.deleted_at.is_(None),
        )
        .all()
    )
    archives_by_id: dict[int, ArchiveFile] = {int(row.id): row for row in archive_rows}

    out: list[dict[str, Any]] = []
    for manifest_row in manifest_rows:
        file_id = int(manifest_row.file_id or 0)
        archive = archives_by_id.get(file_id)
        if not archive:
            continue
        revision = archive.document_revision
        document = revision.document if revision else None
        version_hash = _effective_version_hash(archive, manifest_row=manifest_row)
        if not version_hash:
            continue
        out.append(
            {
                "file_id": file_id,
                "entity_type": ENTITY_ARCHIVE_FILE,
                "project_code": document.project_code if document else None,
                "discipline_code": document.discipline_code if document else None,
                "doc_number": document.doc_number if document else None,
                "revision": archive.revision or (revision.revision if revision else None),
                "status": archive.status,
                "file_kind": archive.file_kind or "pdf",
                "file_name": archive.original_name,
                "relative_path": build_archive_relative_path(archive),
                "version_hash": version_hash,
                "sha256": archive.sha256,
                "size_bytes": archive.size_bytes,
                "uploaded_at": archive.uploaded_at.isoformat() if archive.uploaded_at else None,
                "gdrive_file_id": archive.gdrive_file_id,
                "mirror_provider": getattr(archive, "mirror_provider", None),
                "mirror_remote_id": getattr(archive, "mirror_remote_id", None),
                "mirror_remote_url": getattr(archive, "mirror_remote_url", None),
                "mirror_status": archive.mirror_status,
                "mirror_updated_at": archive.mirror_updated_at.isoformat() if archive.mirror_updated_at else None,
            }
        )
    return out


def detect_matching_profile_by_cidr(
    db: Session,
    *,
    client_ip: str,
    project_code: str | None = None,
) -> tuple[SiteCacheProfile | None, str | None]:
    ip_value = str(client_ip or "").strip()
    if not ip_value:
        return None, None
    try:
        address = ipaddress.ip_address(ip_value)
    except Exception:
        return None, None

    query = (
        db.query(SiteCacheProfile)
        .options(joinedload(SiteCacheProfile.cidrs))
        .filter(SiteCacheProfile.is_active.is_(True))
        .order_by(SiteCacheProfile.id.asc())
    )
    project_key = str(project_code or "").strip().upper()
    if project_key:
        query = query.filter(
            or_(
                SiteCacheProfile.project_code.is_(None),
                SiteCacheProfile.project_code == "",
                func.upper(SiteCacheProfile.project_code) == project_key,
            )
        )

    for profile in query.all():
        for cidr_row in profile.cidrs or []:
            if not cidr_row.is_active:
                continue
            cidr_value = str(cidr_row.cidr or "").strip()
            if not cidr_value:
                continue
            try:
                network = ipaddress.ip_network(cidr_value, strict=False)
            except Exception:
                continue
            if address in network:
                return profile, str(network)
    return None, None


def extract_client_ip(headers: dict[str, str], fallback_ip: str | None = None) -> str:
    forwarded = str(headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        if candidate:
            return candidate
    real_ip = str(headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    return str(fallback_ip or "").strip()


def serialize_profile(profile: SiteCacheProfile) -> dict[str, Any]:
    cidrs = [
        {
            "id": row.id,
            "cidr": row.cidr,
            "is_active": bool(row.is_active),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in sorted(profile.cidrs or [], key=lambda item: (item.id or 0))
    ]
    rules = [
        {
            "id": row.id,
            "name": row.name,
            "project_code": row.project_code,
            "discipline_code": row.discipline_code,
            "package_code": row.package_code,
            "status_codes": row.status_codes,
            "include_native": bool(row.include_native),
            "primary_only": bool(row.primary_only),
            "latest_revision_only": bool(row.latest_revision_only),
            "priority": int(row.priority or 0),
            "is_active": bool(row.is_active),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in sorted(profile.pin_rules or [], key=lambda item: (item.priority, item.id or 0))
    ]
    active_tokens = [row for row in (profile.agent_tokens or []) if row.is_active and row.revoked_at is None]
    return {
        "id": profile.id,
        "code": profile.code,
        "name": profile.name,
        "description": profile.description,
        "project_code": profile.project_code,
        "local_root_path": profile.local_root_path,
        "fallback_mode": profile.fallback_mode,
        "is_active": bool(profile.is_active),
        "last_heartbeat_at": profile.last_heartbeat_at.isoformat() if profile.last_heartbeat_at else None,
        "last_heartbeat_info": _safe_json_dict(profile.last_heartbeat_info),
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        "cidrs": cidrs,
        "rules": rules,
        "active_token_count": len(active_tokens),
    }


def _safe_json_dict(raw: str | None) -> dict[str, Any] | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None
