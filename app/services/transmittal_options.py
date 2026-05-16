from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Organization, SettingsKV

TRANSMITTAL_PARTIES_KEY = "custom.transmittal.parties.v1"

DEFAULT_TRANSMITTAL_PARTIES: dict[str, list[dict[str, Any]]] = {
    "direction_options": [
        {"code": "O", "label": "صادره", "is_active": True, "sort_order": 10},
        {"code": "I", "label": "وارده", "is_active": True, "sort_order": 20},
    ],
    "recipient_options": [
        {"code": "C", "label": "مشاور", "is_active": True, "sort_order": 10},
    ],
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_code(value: Any) -> str:
    return _norm(value).upper()


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return _norm(value).lower() not in {"0", "false", "no", "off", "inactive"}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_options(items: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = items if isinstance(items, list) else fallback
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(source):
        if not isinstance(item, dict):
            continue
        code = _norm_code(item.get("code"))
        if not code or code in seen:
            continue
        label = _norm(item.get("label")) or code
        seen.add(code)
        normalized.append(
            {
                "code": code,
                "label": label,
                "is_active": _as_bool(item.get("is_active"), True),
                "sort_order": _as_int(item.get("sort_order"), (index + 1) * 10),
            }
        )
    if not normalized:
        return [dict(row) for row in fallback]
    return sorted(normalized, key=lambda row: (int(row.get("sort_order") or 0), str(row.get("code") or "")))


def _organization_recipient_options(db: Session, *, active_only: bool) -> list[dict[str, Any]]:
    query = db.query(Organization)
    if active_only:
        query = query.filter(Organization.is_active.is_(True))
    rows = (
        query
        .filter(Organization.org_type != "system")
        .order_by(Organization.name.asc(), Organization.code.asc())
        .all()
    )
    options: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        code = _norm_code(row.code)
        if not code:
            continue
        name = _norm(row.name)
        label = f"{code} - {name}" if name and name.upper() != code else code
        options.append(
            {
                "code": code,
                "label": label,
                "is_active": bool(row.is_active),
                "sort_order": 1000 + ((index + 1) * 10),
                "source": "organization",
                "organization_id": int(row.id or 0),
                "org_type": _norm(row.org_type),
            }
        )
    return options


def _merge_recipient_options(
    configured_options: list[dict[str, Any]],
    organization_options: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in [*configured_options, *organization_options]:
        code = _norm_code(row.get("code"))
        if not code or code in seen:
            continue
        seen.add(code)
        merged.append({**row, "code": code})
    return sorted(merged, key=lambda row: (int(row.get("sort_order") or 0), str(row.get("code") or "")))


def normalize_transmittal_parties_payload(payload: Any) -> dict[str, list[dict[str, Any]]]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "direction_options": _normalize_options(
            data.get("direction_options"),
            DEFAULT_TRANSMITTAL_PARTIES["direction_options"],
        ),
        "recipient_options": _normalize_options(
            data.get("recipient_options"),
            DEFAULT_TRANSMITTAL_PARTIES["recipient_options"],
        ),
    }


def get_transmittal_parties(db: Session) -> dict[str, list[dict[str, Any]]]:
    row = db.query(SettingsKV).filter(SettingsKV.key == TRANSMITTAL_PARTIES_KEY).first()
    if not row or not _norm(row.value):
        return normalize_transmittal_parties_payload(DEFAULT_TRANSMITTAL_PARTIES)
    try:
        raw = json.loads(str(row.value or "{}"))
    except json.JSONDecodeError:
        raw = {}
    return normalize_transmittal_parties_payload(raw)


def set_transmittal_parties(db: Session, payload: Any) -> dict[str, list[dict[str, Any]]]:
    normalized = normalize_transmittal_parties_payload(payload)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    row = db.query(SettingsKV).filter(SettingsKV.key == TRANSMITTAL_PARTIES_KEY).first()
    if row:
        row.value = encoded
        row.updated_at = datetime.utcnow()
    else:
        db.add(SettingsKV(key=TRANSMITTAL_PARTIES_KEY, value=encoded, updated_at=datetime.utcnow()))
    return normalized


def transmittal_options_payload(db: Session, *, active_only: bool = True) -> dict[str, list[dict[str, Any]]]:
    payload = get_transmittal_parties(db)
    if not active_only:
        return payload
    active_payload = {
        key: [row for row in rows if bool(row.get("is_active"))]
        for key, rows in payload.items()
    }
    active_payload["recipient_options"] = _merge_recipient_options(
        active_payload.get("recipient_options") or [],
        _organization_recipient_options(db, active_only=True),
    )
    return active_payload


def transmittal_party_label(db: Session, group: str, code: Any) -> str:
    normalized_code = _norm_code(code)
    if not normalized_code:
        return "-"
    payload = get_transmittal_parties(db)
    rows = payload.get(group) or []
    for row in rows:
        if _norm_code(row.get("code")) == normalized_code:
            return _norm(row.get("label")) or normalized_code
    if group == "recipient_options":
        organization = (
            db.query(Organization)
            .filter(Organization.org_type != "system")
            .filter(func.upper(Organization.code) == normalized_code)
            .first()
        )
        if organization:
            name = _norm(organization.name)
            return f"{normalized_code} - {name}" if name and name.upper() != normalized_code else normalized_code
    return normalized_code
