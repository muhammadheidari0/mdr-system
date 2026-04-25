from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import SettingsKV

STORAGE_POLICY_KEY = "storage_policy.v1"
STORAGE_INTEGRATIONS_KEY = "storage_integrations.v1"
BIM_REVIT_INTEGRATION_KEY = "bim_revit.v1"

DEFAULT_STORAGE_POLICY: dict[str, Any] = {
    "enforcement_mode": "warning",  # warning | enforce
    "allowed_mimes": [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/x-dwg",
        "application/acad",
        "image/vnd.dwg",
        "application/dxf",
        "image/vnd.dxf",
        "model/ifc",
        "application/x-step",
    ],
    "allowed_mimes_by_kind": {
        "pdf": ["application/pdf"],
        "native": [
            "application/pdf",
            "image/png",
            "image/jpeg",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/zip",
            "application/x-dwg",
            "application/acad",
            "image/vnd.dwg",
            "application/dxf",
            "image/vnd.dxf",
            "model/ifc",
            "application/x-step",
            "application/octet-stream",
            "text/plain",
        ],
        "attachment": [
            "application/pdf",
            "image/png",
            "image/jpeg",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/zip",
            "application/x-dwg",
            "application/acad",
            "image/vnd.dwg",
            "application/dxf",
            "image/vnd.dxf",
            "model/ifc",
            "application/x-step",
            "application/octet-stream",
            "text/plain",
        ],
    },
    "blocked_extensions": ["exe", "bat", "cmd", "ps1", "js", "vbs", "sh"],
    "dangerous_mimes": [
        "application/x-msdownload",
        "application/x-dosexec",
        "application/x-executable",
        "application/x-sh",
        "text/x-shellscript",
        "application/x-bat",
    ],
    "max_size_mb": {
        "pdf": 100,
        "native": 250,
        "attachment": 100,
    },
}

DEFAULT_STORAGE_INTEGRATIONS: dict[str, Any] = {
    "primary": {
        "provider": "local",  # local | nextcloud
    },
    "mirror": {
        "provider": "none",  # none | google_drive | nextcloud
    },
    "google_drive": {
        "enabled": False,
        "mirror_mode": "async",
        "shared_drive_id": "",
        "root_folder_id": "",
        "oauth_client_id": "",
        "oauth_client_secret": "",
        "oauth_refresh_token": "",
        "drive_enabled": False,
        "gmail_enabled": False,
        "calendar_enabled": False,
        "sender_email": "",
        "calendar_id": "",
    },
    "openproject": {
        "enabled": False,
        "sync_mode": "link_only",  # link_only | attachment
        "base_url": "",
        "api_token": "",
        "default_work_package_id": "",
        "skip_ssl_verify": None,
    },
    "nextcloud": {
        "enabled": False,
        "mode": "mount",  # mount | webdav
        "base_url": "",
        "username": "",
        "app_password": "",
        "root_path": "",
        "local_mount_root": "",
        "skip_ssl_verify": None,
    },
    "local_cache": {
        "enabled": True,
        "default_scope": "user",
    },
}


DEFAULT_BIM_REVIT_INTEGRATION: dict[str, Any] = {
    "enabled": False,
    "api_endpoint_url": "/api/v1/bim/edms/inbox/publish-batch",
    "require_plugin_signature": True,
    "plugin_key_id": "",
    "plugin_secret_encrypted": "",
    "default_category_id": None,
    "default_folder_id": None,
    "allowed_mime": [
        "application/pdf",
        "application/x-dwg",
        "application/acad",
        "application/octet-stream",
    ],
    "max_batch_size": 100,
}


def _safe_json_load(value: str | None) -> dict[str, Any]:
    raw = str(value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_mime_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values:
        value = str(item or "").strip().lower()
        if not value:
            continue
        if value not in out:
            out.append(value)
    return out


def _to_extension_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values:
        value = str(item or "").strip().lower().lstrip(".")
        if not value:
            continue
        if value not in out:
            out.append(value)
    return out


def _to_non_negative_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return int(fallback)
    return parsed if parsed >= 0 else int(fallback)


def _to_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def _to_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(fallback)


def _normalize_policy(raw: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(DEFAULT_STORAGE_POLICY)
    merged.update({k: v for k, v in raw.items() if k in merged})

    mode = str(merged.get("enforcement_mode") or "").strip().lower()
    merged["enforcement_mode"] = "enforce" if mode == "enforce" else "warning"

    merged["allowed_mimes"] = _to_mime_list(merged.get("allowed_mimes"))
    merged["blocked_extensions"] = _to_extension_list(merged.get("blocked_extensions"))
    merged["dangerous_mimes"] = _to_mime_list(merged.get("dangerous_mimes"))

    allowed_by_kind = merged.get("allowed_mimes_by_kind")
    if not isinstance(allowed_by_kind, dict):
        allowed_by_kind = {}
    normalized_by_kind: dict[str, list[str]] = {}
    for kind in ("pdf", "native", "attachment"):
        normalized_by_kind[kind] = _to_mime_list(allowed_by_kind.get(kind))
    merged["allowed_mimes_by_kind"] = normalized_by_kind

    max_size_mb = merged.get("max_size_mb")
    if not isinstance(max_size_mb, dict):
        max_size_mb = {}
    normalized_sizes = {
        "pdf": _to_non_negative_int(max_size_mb.get("pdf"), 100),
        "native": _to_non_negative_int(max_size_mb.get("native"), 250),
        "attachment": _to_non_negative_int(max_size_mb.get("attachment"), 100),
    }
    merged["max_size_mb"] = normalized_sizes
    return merged


def _normalize_integrations(raw: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(DEFAULT_STORAGE_INTEGRATIONS)
    for top_key in ("primary", "mirror", "google_drive", "openproject", "nextcloud", "local_cache"):
        if isinstance(raw.get(top_key), dict):
            merged[top_key].update(raw[top_key])

    for key in ("google_drive", "openproject", "nextcloud", "local_cache"):
        enabled = bool(merged[key].get("enabled", False))
        merged[key]["enabled"] = enabled

    primary_provider = str(merged.get("primary", {}).get("provider") or "").strip().lower()
    if primary_provider not in {"local", "nextcloud"}:
        primary_provider = "local"
    merged["primary"]["provider"] = primary_provider

    provider = str(merged.get("mirror", {}).get("provider") or "").strip().lower()
    if provider not in {"none", "google_drive", "nextcloud"}:
        provider = "none"
    merged["mirror"]["provider"] = provider

    merged["google_drive"]["mirror_mode"] = (
        "sync" if str(merged["google_drive"].get("mirror_mode") or "").strip().lower() == "sync" else "async"
    )
    merged["openproject"]["sync_mode"] = (
        "attachment"
        if str(merged["openproject"].get("sync_mode") or "").strip().lower() == "attachment"
        else "link_only"
    )
    merged["nextcloud"]["mode"] = (
        "webdav"
        if str(merged["nextcloud"].get("mode") or "").strip().lower() == "webdav"
        else "mount"
    )
    merged["google_drive"]["shared_drive_id"] = str(
        merged["google_drive"].get("shared_drive_id") or ""
    ).strip()
    merged["google_drive"]["root_folder_id"] = str(
        merged["google_drive"].get("root_folder_id") or ""
    ).strip()
    merged["google_drive"]["oauth_client_id"] = str(
        merged["google_drive"].get("oauth_client_id") or ""
    ).strip()
    merged["google_drive"]["oauth_client_secret"] = str(
        merged["google_drive"].get("oauth_client_secret") or ""
    ).strip()
    merged["google_drive"]["oauth_refresh_token"] = str(
        merged["google_drive"].get("oauth_refresh_token") or ""
    ).strip()
    merged["google_drive"]["drive_enabled"] = bool(
        merged["google_drive"].get("drive_enabled", merged["google_drive"].get("enabled"))
    )
    merged["google_drive"]["gmail_enabled"] = bool(merged["google_drive"].get("gmail_enabled"))
    merged["google_drive"]["calendar_enabled"] = bool(merged["google_drive"].get("calendar_enabled"))
    merged["google_drive"]["sender_email"] = str(
        merged["google_drive"].get("sender_email") or ""
    ).strip()
    merged["google_drive"]["calendar_id"] = str(
        merged["google_drive"].get("calendar_id") or ""
    ).strip()
    merged["openproject"]["base_url"] = str(merged["openproject"].get("base_url") or "").strip()
    merged["openproject"]["api_token"] = str(merged["openproject"].get("api_token") or "").strip()
    default_wp = str(
        merged["openproject"].get("default_work_package_id")
        or merged["openproject"].get("default_project_id")
        or ""
    ).strip()
    merged["openproject"]["default_work_package_id"] = default_wp
    merged["openproject"]["skip_ssl_verify"] = _to_optional_bool(merged["openproject"].get("skip_ssl_verify"))
    merged["openproject"].pop("default_project_id", None)
    merged["nextcloud"]["base_url"] = str(merged["nextcloud"].get("base_url") or "").strip()
    merged["nextcloud"]["username"] = str(merged["nextcloud"].get("username") or "").strip()
    merged["nextcloud"]["app_password"] = str(merged["nextcloud"].get("app_password") or "").strip()
    merged["nextcloud"]["root_path"] = str(merged["nextcloud"].get("root_path") or "").strip()
    merged["nextcloud"]["local_mount_root"] = str(
        merged["nextcloud"].get("local_mount_root") or ""
    ).strip()
    merged["nextcloud"]["skip_ssl_verify"] = _to_optional_bool(merged["nextcloud"].get("skip_ssl_verify"))
    merged["local_cache"]["default_scope"] = str(
        merged["local_cache"].get("default_scope") or "user"
    ).strip() or "user"
    return merged


def _normalize_bim_revit(raw: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(DEFAULT_BIM_REVIT_INTEGRATION)
    merged.update({k: v for k, v in raw.items() if k in merged})

    merged["enabled"] = _to_bool(merged.get("enabled"), False)
    merged["api_endpoint_url"] = str(merged.get("api_endpoint_url") or "").strip() or "/api/v1/bim/edms/inbox/publish-batch"
    merged["require_plugin_signature"] = _to_bool(merged.get("require_plugin_signature"), True)
    merged["plugin_key_id"] = str(merged.get("plugin_key_id") or "").strip()
    merged["plugin_secret_encrypted"] = str(merged.get("plugin_secret_encrypted") or "").strip()

    category = merged.get("default_category_id")
    folder = merged.get("default_folder_id")
    try:
        merged["default_category_id"] = int(category) if category is not None and str(category).strip() else None
    except Exception:
        merged["default_category_id"] = None
    try:
        merged["default_folder_id"] = int(folder) if folder is not None and str(folder).strip() else None
    except Exception:
        merged["default_folder_id"] = None

    merged["allowed_mime"] = _to_mime_list(merged.get("allowed_mime"))
    merged["max_batch_size"] = max(1, _to_non_negative_int(merged.get("max_batch_size"), 100))
    return merged


def _get_kv_value(db: Session, key: str) -> str:
    row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    return str(row.value) if row and row.value is not None else ""


def _set_kv_value(db: Session, key: str, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False)
    row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    if row:
        row.value = encoded
        row.updated_at = datetime.utcnow()
        return
    db.add(SettingsKV(key=key, value=encoded, updated_at=datetime.utcnow()))


def get_storage_policy(db: Session) -> dict[str, Any]:
    raw = _safe_json_load(_get_kv_value(db, STORAGE_POLICY_KEY))
    return _normalize_policy(raw)


def set_storage_policy(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_policy(payload)
    _set_kv_value(db, STORAGE_POLICY_KEY, normalized)
    return normalized


def get_storage_integrations(db: Session) -> dict[str, Any]:
    raw = _safe_json_load(_get_kv_value(db, STORAGE_INTEGRATIONS_KEY))
    return _normalize_integrations(raw)


def set_storage_integrations(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_integrations(payload)
    _set_kv_value(db, STORAGE_INTEGRATIONS_KEY, normalized)
    return normalized


def resolve_primary_storage_provider(integrations: dict[str, Any] | None) -> str:
    primary_cfg = dict((integrations or {}).get("primary") or {})
    provider = str(primary_cfg.get("provider") or "").strip().lower()
    if provider == "nextcloud":
        return "nextcloud"
    return "local"


def get_bim_revit_integration(db: Session) -> dict[str, Any]:
    raw = _safe_json_load(_get_kv_value(db, BIM_REVIT_INTEGRATION_KEY))
    return _normalize_bim_revit(raw)


def set_bim_revit_integration(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_bim_revit(payload)
    _set_kv_value(db, BIM_REVIT_INTEGRATION_KEY, normalized)
    return normalized


def policy_size_limit_bytes(policy: dict[str, Any], file_kind: str) -> int:
    kind = str(file_kind or "").strip().lower()
    if kind not in {"pdf", "native", "attachment"}:
        kind = "attachment"
    max_size_mb = policy.get("max_size_mb", {})
    raw = max_size_mb.get(kind)
    limit_mb = _to_non_negative_int(raw, 0)
    return int(limit_mb * 1024 * 1024)


def policy_is_enforced(policy: dict[str, Any]) -> bool:
    return str(policy.get("enforcement_mode") or "").strip().lower() == "enforce"
