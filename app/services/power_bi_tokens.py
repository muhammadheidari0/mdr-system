from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import PowerBiApiToken

POWER_BI_TOKEN_PREFIX = "pbi_edms_"
POWER_BI_SITE_LOG_SCOPE = "site_logs:report_read"
POWER_BI_LAST_USED_THROTTLE = timedelta(minutes=5)


@dataclass(frozen=True)
class PowerBiReportAccess:
    token_id: int
    scopes: list[str]
    allowed_project_codes: list[str]
    allowed_report_sections: list[str]
    allowed_ip_ranges: list[str]

    def has_scope(self, scope: str) -> bool:
        return str(scope or "").strip() in set(self.scopes)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def is_power_bi_token_value(value: str | None) -> bool:
    return str(value or "").strip().startswith(POWER_BI_TOKEN_PREFIX)


def mint_power_bi_token_value() -> str:
    return f"{POWER_BI_TOKEN_PREFIX}{secrets.token_urlsafe(48)}"


def hash_power_bi_token(token: str) -> str:
    raw = str(token or "").strip()
    secret = str(settings.SECRET_KEY or "").strip()
    if not raw or not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def power_bi_token_hint(token: str) -> str:
    raw = str(token or "").strip()
    if len(raw) <= 18:
        return raw
    return f"{POWER_BI_TOKEN_PREFIX}...{raw[-6:]}"


def _json_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw = values.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = [part.strip() for part in raw.split(",")]
    else:
        parsed = values
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _dump_list(values: Iterable[str] | None, *, upper: bool = False, lower: bool = False) -> str | None:
    out: list[str] = []
    for item in values or []:
        text = str(item or "").strip()
        if not text:
            continue
        if upper:
            text = text.upper()
        if lower:
            text = text.lower()
        if text not in out:
            out.append(text)
    return json.dumps(out, ensure_ascii=False) if out else None


def _normalize_report_sections(values: Iterable[str] | None) -> list[str]:
    allowed = {"general", "manpower", "equipment", "material", "activity"}
    out: list[str] = []
    for item in values or []:
        text = str(item or "").strip().lower()
        if text in allowed and text not in out:
            out.append(text)
    return out


def _ip_allowed(ip_value: str | None, ranges: list[str]) -> bool:
    if not ranges:
        return True
    try:
        client_ip = ipaddress.ip_address(str(ip_value or "").strip())
    except ValueError:
        return False
    for raw in ranges:
        try:
            network = ipaddress.ip_network(str(raw or "").strip(), strict=False)
        except ValueError:
            continue
        if client_ip in network:
            return True
    return False


def serialize_power_bi_token(row: PowerBiApiToken) -> dict[str, Any]:
    scopes = _json_list(row.scopes)
    return {
        "id": row.id,
        "name": row.name,
        "token_hint": row.token_hint,
        "scopes": scopes or [POWER_BI_SITE_LOG_SCOPE],
        "allowed_project_codes": _json_list(row.allowed_project_codes),
        "allowed_report_sections": _json_list(row.allowed_report_sections),
        "allowed_ip_ranges": _json_list(row.allowed_ip_ranges),
        "is_active": bool(row.is_active),
        "created_by_id": row.created_by_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


def access_from_power_bi_token(row: PowerBiApiToken) -> PowerBiReportAccess:
    scopes = _json_list(row.scopes) or [POWER_BI_SITE_LOG_SCOPE]
    return PowerBiReportAccess(
        token_id=int(row.id),
        scopes=scopes,
        allowed_project_codes=[item.upper() for item in _json_list(row.allowed_project_codes)],
        allowed_report_sections=[item.lower() for item in _json_list(row.allowed_report_sections)],
        allowed_ip_ranges=_json_list(row.allowed_ip_ranges),
    )


def create_power_bi_token(
    db: Session,
    *,
    name: str,
    created_by_id: int | None = None,
    expires_at: datetime | None = None,
    allowed_project_codes: Iterable[str] | None = None,
    allowed_report_sections: Iterable[str] | None = None,
    allowed_ip_ranges: Iterable[str] | None = None,
) -> tuple[PowerBiApiToken, str]:
    raw_token = mint_power_bi_token_value()
    token_hash = hash_power_bi_token(raw_token)
    if not token_hash:
        raise HTTPException(status_code=500, detail="Power BI token secret is not configured.")

    sections = _normalize_report_sections(allowed_report_sections)
    row = PowerBiApiToken(
        token_hash=token_hash,
        token_hint=power_bi_token_hint(raw_token),
        name=str(name or "").strip() or "Power BI",
        scopes=json.dumps([POWER_BI_SITE_LOG_SCOPE], ensure_ascii=False),
        allowed_project_codes=_dump_list(allowed_project_codes, upper=True),
        allowed_report_sections=_dump_list(sections, lower=True),
        allowed_ip_ranges=_dump_list(allowed_ip_ranges),
        is_active=True,
        created_by_id=created_by_id,
        expires_at=_to_naive_utc(expires_at),
    )
    db.add(row)
    db.flush()
    return row, raw_token


def resolve_power_bi_report_access(
    db: Session,
    *,
    token_value: str,
    client_ip: str | None = None,
    required_scope: str = POWER_BI_SITE_LOG_SCOPE,
) -> tuple[PowerBiApiToken, PowerBiReportAccess]:
    if not is_power_bi_token_value(token_value):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Power BI token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_hash = hash_power_bi_token(token_value)
    if not token_hash:
        raise HTTPException(status_code=500, detail="Power BI token secret is not configured.")

    row = (
        db.query(PowerBiApiToken)
        .filter(
            PowerBiApiToken.token_hash == token_hash,
            PowerBiApiToken.is_active.is_(True),
            PowerBiApiToken.revoked_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Power BI token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = _utcnow()
    if row.expires_at and row.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Power BI token expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access = access_from_power_bi_token(row)
    if not access.has_scope(required_scope):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Power BI token scope is not allowed.")
    if not _ip_allowed(client_ip, access.allowed_ip_ranges):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Power BI token is not allowed from this IP.")

    if row.last_used_at is None or now - row.last_used_at >= POWER_BI_LAST_USED_THROTTLE:
        row.last_used_at = now
        db.commit()
        db.refresh(row)

    return row, access
