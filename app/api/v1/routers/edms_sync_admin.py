from __future__ import annotations

from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_permission
from app.core.config import settings
from app.services.edms_export_manifest import export_archive_manifest_rows
from app.services.edms_sync_outbox import EVENT_ENDPOINTS, build_master_data_snapshot, build_sync_envelopes


router = APIRouter(prefix="/edms-sync", tags=["Native EDMS Sync"])


class NativeEdmsPushRequest(BaseModel):
    target_url: str | None = Field(default=None, max_length=2048)
    secret: str | None = Field(default=None, max_length=512)
    dry_run: bool = Field(default=True)
    include: list[str] | None = Field(default=None)
    timeout_seconds: int | None = Field(default=None, ge=1, le=120)


def _resolved_secret(payload: NativeEdmsPushRequest) -> str:
    return str(payload.secret or settings.NATIVE_EDMS_SYNC_SHARED_SECRET or "").strip()


def _resolved_target_url(payload: NativeEdmsPushRequest) -> str:
    return str(payload.target_url or settings.NATIVE_EDMS_SYNC_TARGET_URL or "").strip().rstrip("/")


@router.get("/master-data-snapshot")
def get_native_edms_master_data_snapshot(
    db: Session = Depends(get_db),
    _: object = Depends(require_permission("integrations:read")),
):
    return {
        "ok": True,
        "snapshot": build_master_data_snapshot(db),
    }


@router.get("/archive-manifest")
def get_native_edms_archive_manifest(
    project_code: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: object = Depends(require_permission("integrations:read")),
):
    rows = export_archive_manifest_rows(db, project_code=project_code, limit=limit)
    return {
        "ok": True,
        "count": len(rows),
        "items": rows,
    }


@router.get("/event-preview")
def preview_native_edms_sync_events(
    include: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    _: object = Depends(require_permission("integrations:read")),
):
    secret = str(settings.NATIVE_EDMS_SYNC_SHARED_SECRET or "").strip()
    if not secret:
        raise HTTPException(status_code=400, detail="NATIVE_EDMS_SYNC_SHARED_SECRET is not configured.")
    envelopes = build_sync_envelopes(db, secret=secret, source=settings.NATIVE_EDMS_SYNC_SOURCE)
    if include:
        envelopes = {key: value for key, value in envelopes.items() if key in set(include)}
    return {
        "ok": True,
        "events": envelopes,
        "target_endpoints": {key: EVENT_ENDPOINTS.get(key) for key in envelopes.keys()},
    }


@router.post("/push")
def push_native_edms_sync_events(
    payload: NativeEdmsPushRequest,
    db: Session = Depends(get_db),
    _: object = Depends(require_permission("integrations:update")),
):
    secret = _resolved_secret(payload)
    if not secret:
        raise HTTPException(status_code=400, detail="Sync secret is required.")
    envelopes = build_sync_envelopes(db, secret=secret, source=settings.NATIVE_EDMS_SYNC_SOURCE)
    if payload.include:
        envelopes = {key: value for key, value in envelopes.items() if key in set(payload.include)}

    if payload.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "events": envelopes,
        }

    target_url = _resolved_target_url(payload)
    if not target_url:
        raise HTTPException(status_code=400, detail="Target URL is required for push.")

    timeout_seconds = int(payload.timeout_seconds or settings.NATIVE_EDMS_SYNC_TIMEOUT_SECONDS or 15)
    results: list[dict[str, Any]] = []
    for entity, envelope in envelopes.items():
        endpoint = EVENT_ENDPOINTS.get(entity)
        if not endpoint:
            continue
        url = f"{target_url}{endpoint}"
        try:
            response = requests.post(url, json=envelope, timeout=timeout_seconds)
            results.append(
                {
                    "entity": entity,
                    "url": url,
                    "status_code": int(response.status_code),
                    "ok": bool(response.ok),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "entity": entity,
                    "url": url,
                    "ok": False,
                    "error": str(exc),
                }
            )
    return {
        "ok": all(bool(item.get("ok")) for item in results),
        "dry_run": False,
        "results": results,
    }
