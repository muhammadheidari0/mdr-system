from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import User, get_db, require_permission
from app.db.models import (
    SiteCacheAgentToken,
    SiteCachePinRule,
    SiteCacheProfile,
    SiteCacheProfileCIDR,
)
from app.services.site_cache import (
    DEFAULT_FALLBACK_MODE,
    DEFAULT_SITE_RULE_STATUSES,
    agent_token_hint,
    hash_agent_token,
    mint_agent_token_value,
    normalize_cidr,
    normalize_csv_codes,
    normalize_fallback_mode,
    normalize_site_code,
    rebuild_profile_manifest,
    serialize_profile,
)


router = APIRouter(
    prefix="/settings/site-cache",
    tags=["settings-site-cache"],
    dependencies=[Depends(require_permission("site_cache:read"))],
)


class SiteCacheProfileIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    project_code: Optional[str] = Field(default=None, max_length=50)
    local_root_path: Optional[str] = Field(default=None, max_length=1024)
    fallback_mode: Optional[str] = Field(default=DEFAULT_FALLBACK_MODE, max_length=32)
    is_active: bool = True


class SiteCacheProfileDeleteIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    code: Optional[str] = Field(default=None, min_length=2, max_length=64)
    hard_delete: bool = False


class SiteCacheCIDRIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    profile_id: int = Field(..., ge=1)
    cidr: str = Field(..., min_length=3, max_length=64)
    is_active: bool = True


class SiteCacheCIDRDeleteIn(BaseModel):
    id: int = Field(..., ge=1)


class SiteCacheRuleIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    profile_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=255)
    project_code: Optional[str] = Field(default=None, max_length=50)
    discipline_code: Optional[str] = Field(default=None, max_length=20)
    package_code: Optional[str] = Field(default=None, max_length=30)
    status_codes: Optional[str] = Field(default=DEFAULT_SITE_RULE_STATUSES, max_length=255)
    include_native: bool = False
    primary_only: bool = True
    latest_revision_only: bool = True
    priority: int = Field(default=100, ge=0, le=10000)
    is_active: bool = True


class SiteCacheRuleDeleteIn(BaseModel):
    id: int = Field(..., ge=1)


class SiteCacheTokenMintIn(BaseModel):
    profile_id: int = Field(..., ge=1)
    description: Optional[str] = Field(default=None, max_length=255)


class SiteCacheTokenRevokeIn(BaseModel):
    token_id: int = Field(..., ge=1)


class SiteCacheRebuildPinsIn(BaseModel):
    profile_id: int = Field(..., ge=1)
    dry_run: bool = False


def _normalize_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def _load_profile(db: Session, *, profile_id: int | None = None, code: str | None = None) -> SiteCacheProfile:
    query = (
        db.query(SiteCacheProfile)
        .options(
            joinedload(SiteCacheProfile.cidrs),
            joinedload(SiteCacheProfile.pin_rules),
            joinedload(SiteCacheProfile.agent_tokens),
        )
    )
    row: SiteCacheProfile | None = None
    if profile_id:
        row = query.filter(SiteCacheProfile.id == int(profile_id)).first()
    elif code:
        row = query.filter(SiteCacheProfile.code == normalize_site_code(code)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Site cache profile not found")
    return row


@router.get("/profiles")
def list_profiles(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    query = (
        db.query(SiteCacheProfile)
        .options(
            joinedload(SiteCacheProfile.cidrs),
            joinedload(SiteCacheProfile.pin_rules),
            joinedload(SiteCacheProfile.agent_tokens),
        )
        .order_by(SiteCacheProfile.id.asc())
    )
    if not include_inactive:
        query = query.filter(SiteCacheProfile.is_active.is_(True))
    rows = query.all()
    return {"ok": True, "items": [serialize_profile(row) for row in rows]}


@router.post("/profiles/upsert")
def upsert_profile(
    payload: SiteCacheProfileIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    code = normalize_site_code(payload.code)
    if not code:
        raise HTTPException(status_code=400, detail="Invalid profile code")

    row: SiteCacheProfile | None = None
    if payload.id:
        row = db.query(SiteCacheProfile).filter(SiteCacheProfile.id == int(payload.id)).first()
    if row is None:
        row = db.query(SiteCacheProfile).filter(SiteCacheProfile.code == code).first()

    if row is None:
        row = SiteCacheProfile(code=code, name=payload.name.strip())
        db.add(row)
        db.flush()

    row.code = code
    row.name = str(payload.name or "").strip()
    row.description = str(payload.description or "").strip() or None
    row.project_code = _normalize_code(payload.project_code) or None
    row.local_root_path = str(payload.local_root_path or "").strip() or None
    row.fallback_mode = normalize_fallback_mode(payload.fallback_mode)
    row.is_active = bool(payload.is_active)
    row.updated_at = datetime.utcnow()
    db.commit()

    saved = _load_profile(db, profile_id=row.id)
    return {"ok": True, "item": serialize_profile(saved)}


@router.post("/profiles/delete")
def delete_profile(
    payload: SiteCacheProfileDeleteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    if not payload.id and not payload.code:
        raise HTTPException(status_code=400, detail="Either id or code is required")

    row = _load_profile(db, profile_id=payload.id, code=payload.code)
    if payload.hard_delete:
        db.delete(row)
    else:
        row.is_active = False
        row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.get("/cidrs")
def list_profile_cidrs(
    profile_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    _load_profile(db, profile_id=profile_id)
    rows = (
        db.query(SiteCacheProfileCIDR)
        .filter(SiteCacheProfileCIDR.profile_id == int(profile_id))
        .order_by(SiteCacheProfileCIDR.id.asc())
        .all()
    )
    items = [
        {
            "id": row.id,
            "profile_id": row.profile_id,
            "cidr": row.cidr,
            "is_active": bool(row.is_active),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
    return {"ok": True, "items": items}


@router.post("/cidrs/upsert")
def upsert_profile_cidr(
    payload: SiteCacheCIDRIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    _load_profile(db, profile_id=payload.profile_id)
    try:
        cidr = normalize_cidr(payload.cidr)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CIDR: {payload.cidr}") from exc
    if not cidr:
        raise HTTPException(status_code=400, detail="Invalid CIDR")

    row: SiteCacheProfileCIDR | None = None
    if payload.id:
        row = (
            db.query(SiteCacheProfileCIDR)
            .filter(SiteCacheProfileCIDR.id == int(payload.id))
            .first()
        )
    if row is None:
        row = (
            db.query(SiteCacheProfileCIDR)
            .filter(
                SiteCacheProfileCIDR.profile_id == int(payload.profile_id),
                SiteCacheProfileCIDR.cidr == cidr,
            )
            .first()
        )

    if row is None:
        row = SiteCacheProfileCIDR(profile_id=int(payload.profile_id), cidr=cidr)
        db.add(row)
        db.flush()

    row.profile_id = int(payload.profile_id)
    row.cidr = cidr
    row.is_active = bool(payload.is_active)
    db.commit()

    return {
        "ok": True,
        "item": {
            "id": row.id,
            "profile_id": row.profile_id,
            "cidr": row.cidr,
            "is_active": bool(row.is_active),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    }


@router.post("/cidrs/delete")
def delete_profile_cidr(
    payload: SiteCacheCIDRDeleteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    row = db.query(SiteCacheProfileCIDR).filter(SiteCacheProfileCIDR.id == int(payload.id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="CIDR row not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/rules")
def list_pin_rules(
    profile_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    _load_profile(db, profile_id=profile_id)
    rows = (
        db.query(SiteCachePinRule)
        .filter(SiteCachePinRule.profile_id == int(profile_id))
        .order_by(SiteCachePinRule.priority.asc(), SiteCachePinRule.id.asc())
        .all()
    )
    items = [
        {
            "id": row.id,
            "profile_id": row.profile_id,
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
        for row in rows
    ]
    return {"ok": True, "items": items}


@router.post("/rules/upsert")
def upsert_pin_rule(
    payload: SiteCacheRuleIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    _load_profile(db, profile_id=payload.profile_id)
    row: SiteCachePinRule | None = None
    if payload.id:
        row = db.query(SiteCachePinRule).filter(SiteCachePinRule.id == int(payload.id)).first()
    if row is None:
        row = SiteCachePinRule(profile_id=int(payload.profile_id), name=str(payload.name or "").strip())
        db.add(row)
        db.flush()

    package_code = _normalize_code(payload.package_code) or None
    discipline_code = _normalize_code(payload.discipline_code) or None
    if package_code and not discipline_code:
        raise HTTPException(status_code=400, detail="discipline_code is required when package_code is set")

    row.profile_id = int(payload.profile_id)
    row.name = str(payload.name or "").strip()
    row.project_code = _normalize_code(payload.project_code) or None
    row.discipline_code = discipline_code
    row.package_code = package_code
    row.status_codes = normalize_csv_codes(payload.status_codes or DEFAULT_SITE_RULE_STATUSES, uppercase=True)
    row.include_native = bool(payload.include_native)
    row.primary_only = bool(payload.primary_only)
    row.latest_revision_only = True
    row.priority = int(payload.priority or 0)
    row.is_active = bool(payload.is_active)
    row.updated_at = datetime.utcnow()
    db.commit()

    return {
        "ok": True,
        "item": {
            "id": row.id,
            "profile_id": row.profile_id,
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
        },
    }


@router.post("/rules/delete")
def delete_pin_rule(
    payload: SiteCacheRuleDeleteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    row = db.query(SiteCachePinRule).filter(SiteCachePinRule.id == int(payload.id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/tokens")
def list_agent_tokens(
    profile_id: int = Query(..., ge=1),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    _load_profile(db, profile_id=profile_id)
    query = db.query(SiteCacheAgentToken).filter(SiteCacheAgentToken.profile_id == int(profile_id))
    if not include_inactive:
        query = query.filter(
            SiteCacheAgentToken.is_active.is_(True),
            SiteCacheAgentToken.revoked_at.is_(None),
        )
    rows = query.order_by(SiteCacheAgentToken.id.desc()).all()
    items = [
        {
            "id": row.id,
            "profile_id": row.profile_id,
            "token_hint": row.token_hint,
            "description": row.description,
            "is_active": bool(row.is_active),
            "created_by_id": row.created_by_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        }
        for row in rows
    ]
    return {"ok": True, "items": items}


@router.post("/tokens/mint")
def mint_agent_token(
    payload: SiteCacheTokenMintIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    profile = _load_profile(db, profile_id=payload.profile_id)
    if not profile.is_active:
        raise HTTPException(status_code=400, detail="Profile is inactive")

    raw_token = mint_agent_token_value()
    hashed = hash_agent_token(raw_token)
    token_row = SiteCacheAgentToken(
        profile_id=profile.id,
        token_hash=hashed,
        token_hint=agent_token_hint(raw_token),
        description=str(payload.description or "").strip() or None,
        is_active=True,
        created_by_id=int(user.id or 0) if getattr(user, "id", None) else None,
    )
    db.add(token_row)
    db.commit()
    db.refresh(token_row)
    return {
        "ok": True,
        "item": {
            "id": token_row.id,
            "profile_id": token_row.profile_id,
            "token_hint": token_row.token_hint,
            "description": token_row.description,
            "created_at": token_row.created_at.isoformat() if token_row.created_at else None,
            "is_active": bool(token_row.is_active),
        },
        "token": raw_token,
        "warning": "Token is shown once. Save it securely now.",
    }


@router.post("/tokens/revoke")
def revoke_agent_token(
    payload: SiteCacheTokenRevokeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    row = db.query(SiteCacheAgentToken).filter(SiteCacheAgentToken.id == int(payload.token_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Token not found")
    row.is_active = False
    row.revoked_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/rebuild-pins")
def rebuild_site_pins(
    payload: SiteCacheRebuildPinsIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_cache:manage")),
):
    del user
    profile = _load_profile(db, profile_id=payload.profile_id)
    result = rebuild_profile_manifest(db, profile, dry_run=bool(payload.dry_run))
    if not payload.dry_run:
        db.commit()
    return {"ok": True, "profile": {"id": profile.id, "code": profile.code}, "result": result}
