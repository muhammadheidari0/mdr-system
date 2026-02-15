from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.db.models import OpenProjectLink
from app.services.storage_policy import get_storage_integrations

ENTITY_ARCHIVE_FILE = "archive_file"
ENTITY_CORRESPONDENCE_ATTACHMENT = "correspondence_attachment"

OPENPROJECT_STATUS_SYNCED = "synced"
OPENPROJECT_STATUS_PENDING = "pending"
OPENPROJECT_STATUS_FAILED = "failed"
OPENPROJECT_STATUS_DISABLED = "disabled"
OPENPROJECT_STATUS_NOT_LINKED = "not_linked"

_VALID_ENTITY_TYPES = {
    ENTITY_ARCHIVE_FILE,
    ENTITY_CORRESPONDENCE_ATTACHMENT,
}
_VALID_SYNC_STATUSES = {
    OPENPROJECT_STATUS_SYNCED,
    OPENPROJECT_STATUS_PENDING,
    OPENPROJECT_STATUS_FAILED,
    OPENPROJECT_STATUS_DISABLED,
    OPENPROJECT_STATUS_NOT_LINKED,
}


def normalize_entity_type(value: str | None, default: str = ENTITY_ARCHIVE_FILE) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"archive_file", "archive", "file"}:
        return ENTITY_ARCHIVE_FILE
    if raw in {"correspondence_attachment", "attachment", "corr_attachment"}:
        return ENTITY_CORRESPONDENCE_ATTACHMENT
    return default


def is_valid_entity_type(value: str | None) -> bool:
    return normalize_entity_type(value, default="") in _VALID_ENTITY_TYPES


def normalize_openproject_sync_status(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"ok", "done"}:
        raw = OPENPROJECT_STATUS_SYNCED
    if raw in {"error", "retry", "dead"}:
        raw = OPENPROJECT_STATUS_FAILED
    if raw not in _VALID_SYNC_STATUSES:
        return OPENPROJECT_STATUS_PENDING
    return raw


def is_openproject_integration_enabled(db: Session) -> bool:
    integrations = get_storage_integrations(db)
    return bool((integrations.get("openproject") or {}).get("enabled"))


def default_openproject_sync_status(*, integration_enabled: bool) -> str:
    return OPENPROJECT_STATUS_NOT_LINKED if integration_enabled else OPENPROJECT_STATUS_DISABLED


def _row_sort_key(row: OpenProjectLink) -> tuple[datetime, int]:
    return (row.last_synced_at or datetime.min, int(row.id or 0))


def get_openproject_status_map(
    db: Session,
    items: Iterable[tuple[str, int]],
    *,
    integration_enabled: bool | None = None,
) -> dict[tuple[str, int], dict[str, Any]]:
    normalized_items: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for entity_type, entity_id in items:
        normalized_entity = normalize_entity_type(entity_type, default="")
        entity_int = int(entity_id or 0)
        if normalized_entity not in _VALID_ENTITY_TYPES or entity_int <= 0:
            continue
        key = (normalized_entity, entity_int)
        if key in seen:
            continue
        seen.add(key)
        normalized_items.append(key)

    if not normalized_items:
        return {}

    if integration_enabled is None:
        integration_enabled = is_openproject_integration_enabled(db)
    fallback_status = default_openproject_sync_status(integration_enabled=bool(integration_enabled))

    entity_types = sorted({entity_type for entity_type, _ in normalized_items})
    entity_ids = sorted({entity_id for _, entity_id in normalized_items})

    rows = (
        db.query(OpenProjectLink)
        .filter(OpenProjectLink.entity_type.in_(entity_types))
        .filter(OpenProjectLink.entity_id.in_(entity_ids))
        .all()
    )

    latest_by_key: dict[tuple[str, int], OpenProjectLink] = {}
    for row in rows:
        key = (normalize_entity_type(row.entity_type, default=""), int(row.entity_id or 0))
        if key not in seen:
            continue
        current = latest_by_key.get(key)
        if not current or _row_sort_key(row) > _row_sort_key(current):
            latest_by_key[key] = row

    payload: dict[tuple[str, int], dict[str, Any]] = {}
    for key in normalized_items:
        row = latest_by_key.get(key)
        if not row:
            payload[key] = {
                "sync_status": fallback_status,
                "work_package_id": None,
                "openproject_attachment_id": None,
                "last_synced_at": None,
            }
            continue
        payload[key] = {
            "sync_status": normalize_openproject_sync_status(row.sync_status),
            "work_package_id": int(row.work_package_id or 0) or None,
            "openproject_attachment_id": str(row.openproject_attachment_id or "").strip() or None,
            "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
        }
    return payload
