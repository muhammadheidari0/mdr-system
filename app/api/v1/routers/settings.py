# app/api/v1/routers/settings.py
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
import traceback  # ✅ برای لاگ خطاهای دقیق

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import get_db, allow_admin
from app.core.config import settings
from app.core.roles import ALL_ROLES, ROLE_PERMISSIONS, Role, normalize_role
from app.db.models import (
    Project, Phase, Discipline, Package, Level,
    SettingsKV, Block, MdrCategory, DocStatus, User as DbUser,
    RolePermission, RoleProjectScope, RoleDisciplineScope,
    UserProjectScope, UserDisciplineScope,
    SettingsAuditLog,
    Correspondence, CorrespondenceAction, CorrespondenceAttachment,
)

# ✅ استفاده از سرویس Seed
from app.services import seed_service

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(allow_admin)])

KV_RESERVED_KEYS = {
    "transmittal.state.v1",
    "rbac.matrix.v1",
    "rbac.scope.v1",
    "rbac.user_scope.v1",
}
KV_ALLOWED_WRITE_PREFIXES = ("ui.", "feature.", "custom.")
STORAGE_PATH_MDR_KEY = "mdr_storage_path"
STORAGE_PATH_CORRESPONDENCE_KEY = "correspondence_storage_path"
DEFAULT_MDR_STORAGE_PATH = "./files/technical"
DEFAULT_CORRESPONDENCE_STORAGE_PATH = "./files/correspondence"


# -----------------------------
# Pydantic Schemas
# -----------------------------
class ProjectIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name_e: Optional[str] = Field(default=None, max_length=255)
    name_p: Optional[str] = Field(default=None, max_length=255)
    project_name: Optional[str] = Field(default=None, max_length=255)
    root_path: Optional[str] = Field(default=None, max_length=1024)
    is_active: Optional[bool] = None
    docnum_template: Optional[str] = Field(default=None, max_length=2000)

class PhaseIn(BaseModel):
    ph_code: str = Field(..., min_length=1, max_length=10)
    name_e: str = Field(..., min_length=1, max_length=255)
    name_p: str = Field(..., min_length=1, max_length=255)

class DisciplineIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name_e: str = Field(..., min_length=1, max_length=255)
    name_p: Optional[str] = Field(default=None, max_length=255)

class PackageIn(BaseModel):
    discipline_code: str = Field(..., min_length=1, max_length=20)
    package_code: str = Field(..., min_length=1, max_length=30)
    name_e: str = Field(..., min_length=1, max_length=255)
    name_p: Optional[str] = Field(default=None, max_length=255)

class LevelIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name_e: Optional[str] = Field(default=None, max_length=255)
    name_p: Optional[str] = Field(default=None, max_length=255)
    sort_order: int = 0

class LevelDeleteIn(BaseModel):
    code: str

class KvIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=120)
    value: str = Field(..., min_length=0, max_length=5000)

class StoragePathsIn(BaseModel):
    mdr_storage_path: str = Field(..., min_length=1, max_length=1024)
    correspondence_storage_path: str = Field(..., min_length=1, max_length=1024)

class BlockIn(BaseModel):
    project_code: str = Field(..., min_length=1, max_length=50)
    code: str = Field(..., min_length=1, max_length=10)
    name_e: Optional[str] = Field(default=None, max_length=255)
    name_p: Optional[str] = Field(default=None, max_length=255)
    sort_order: int = 0
    is_active: bool = True

class BlockDeleteIn(BaseModel):
    project_code: str
    code: str
    hard_delete: bool = False

class MdrCategoryIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=10)
    name_e: str = Field(..., min_length=1, max_length=255)
    name_p: Optional[str] = Field(default=None, max_length=255)
    folder_name: Optional[str] = Field(default=None, max_length=255)
    sort_order: int = 0
    is_active: bool = True

class MdrCategoryDeleteIn(BaseModel):
    code: str
    hard_delete: bool = False

class ProjectDeleteIn(BaseModel):
    code: str
    hard_delete: bool = False

class PhaseDeleteIn(BaseModel):
    ph_code: str

class DisciplineDeleteIn(BaseModel):
    code: str

class PackageDeleteIn(BaseModel):
    discipline_code: str
    package_code: str

class DocStatusIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)
    sort_order: int = 0

class DocStatusDeleteIn(BaseModel):
    code: str


class PermissionMatrixIn(BaseModel):
    matrix: Dict[str, Dict[str, bool]]


class PermissionScopeIn(BaseModel):
    scope: Dict[str, Dict[str, List[str]]]


class UserPermissionScopeIn(BaseModel):
    user_id: int
    projects: List[str] = Field(default_factory=list)
    disciplines: List[str] = Field(default_factory=list)


# -----------------------------
# Helpers
# -----------------------------
def _norm(s: Any) -> str:
    if s is None: return ""
    return str(s).strip()

def _upper(s: Any) -> str:
    return _norm(s).upper()

def _count(db: Session, model) -> int:
    return db.query(model).count()


def _safe_json_dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _as_dict(obj: Any, fields: List[str]) -> Dict[str, Any] | None:
    if obj is None:
        return None
    return {field: getattr(obj, field, None) for field in fields}


def _audit_log(
    db: Session,
    *,
    actor: DbUser,
    action: str,
    target_type: str,
    target_key: str | None,
    before: Any,
    after: Any,
) -> None:
    db.add(
        SettingsAuditLog(
            action=action,
            target_type=target_type,
            target_key=_norm(target_key) or None,
            actor_user_id=actor.id,
            actor_email=actor.email,
            actor_name=actor.full_name,
            before_json=_safe_json_dump(before),
            after_json=_safe_json_dump(after),
            created_at=datetime.utcnow(),
        )
    )


def _effective_scope_values(role_values: List[str], user_values: List[str]) -> tuple[List[str], bool]:
    role_set = set(role_values)
    user_set = set(user_values)
    if role_set and user_set:
        return sorted(role_set & user_set), True
    if role_set:
        return sorted(role_set), True
    if user_set:
        return sorted(user_set), True
    return [], False


def _build_access_report_items(
    db: Session,
    *,
    project_code: Optional[str],
    discipline_code: Optional[str],
    include_inactive: bool,
    include_denied: bool,
) -> List[Dict[str, Any]]:
    project = _upper(project_code)
    discipline = _upper(discipline_code)
    role_scope = _load_scope_rules(db)
    user_scope = _load_user_scope_rules(db)

    q = db.query(DbUser).order_by(DbUser.id)
    if not include_inactive:
        q = q.filter(DbUser.is_active == True)
    users = q.all()

    items: List[Dict[str, Any]] = []
    for user in users:
        role = normalize_role(user.role)
        project_allowed = True
        discipline_allowed = True
        has_access = True
        effective_projects: List[str] = []
        effective_disciplines: List[str] = []
        project_restricted = False
        discipline_restricted = False

        if role != Role.ADMIN.value:
            role_projects = role_scope.get(role, {}).get("projects", [])
            role_disciplines = role_scope.get(role, {}).get("disciplines", [])
            user_projects = user_scope.get(str(user.id), {}).get("projects", [])
            user_disciplines = user_scope.get(str(user.id), {}).get("disciplines", [])

            effective_projects, project_restricted = _effective_scope_values(role_projects, user_projects)
            effective_disciplines, discipline_restricted = _effective_scope_values(role_disciplines, user_disciplines)

            if project and project_restricted:
                project_allowed = project in effective_projects
            if discipline and discipline_restricted:
                discipline_allowed = discipline in effective_disciplines
            has_access = bool(project_allowed and discipline_allowed)

        if has_access or include_denied:
            items.append(
                {
                    "user_id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": role,
                    "is_active": user.is_active,
                    "has_access": has_access,
                    "project_allowed": project_allowed,
                    "discipline_allowed": discipline_allowed,
                    "projects_restricted": project_restricted,
                    "disciplines_restricted": discipline_restricted,
                    "effective_projects": effective_projects,
                    "effective_disciplines": effective_disciplines,
                }
            )
    return items


# -----------------------------
# KV Helpers
# -----------------------------
def _kv_set(db: Session, key: str, value: str) -> None:
    kv = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    if kv:
        kv.value = value
        kv.updated_at = datetime.utcnow()
    else:
        kv = SettingsKV(key=key, value=value, updated_at=datetime.utcnow())
        db.add(kv)

def _kv_get_all(db: Session, *, include_legacy: bool = False) -> List[Dict[str, Any]]:
    rows = db.query(SettingsKV).order_by(SettingsKV.key).all()
    if not include_legacy:
        rows = [
            r for r in rows
            if r.key not in KV_RESERVED_KEYS and not str(r.key or "").startswith("legacy.")
        ]
    return [{"key": r.key, "value": r.value, "updated_at": r.updated_at.isoformat()} for r in rows]


def _kv_get_value(db: Session, key: str, default: str = "") -> str:
    row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    if not row:
        return default
    value = _norm(row.value)
    return value if value else default


def _is_allowed_kv_write_key(key: str) -> bool:
    if key in KV_RESERVED_KEYS:
        return False
    if key.startswith("legacy."):
        return False
    return any(key.startswith(prefix) for prefix in KV_ALLOWED_WRITE_PREFIXES)


def _permission_keys() -> List[str]:
    keys: set[str] = set()
    for perms in ROLE_PERMISSIONS.values():
        for perm in perms:
            if perm != "*":
                keys.add(perm)
    return sorted(keys)


def _default_permission_matrix() -> Dict[str, Dict[str, bool]]:
    perms = _permission_keys()
    matrix: Dict[str, Dict[str, bool]] = {}
    for role in ALL_ROLES:
        role_enum = Role(role)
        role_permissions = ROLE_PERMISSIONS.get(role_enum, [])
        if "*" in role_permissions:
            matrix[role] = {perm: True for perm in perms}
        else:
            matrix[role] = {perm: perm in role_permissions for perm in perms}
    return matrix


def _normalize_permission_matrix(raw: Any) -> Dict[str, Dict[str, bool]]:
    normalized = _default_permission_matrix()
    perms = _permission_keys()

    if not isinstance(raw, dict):
        return normalized

    for role in ALL_ROLES:
        if role == Role.ADMIN.value:
            normalized[role] = {perm: True for perm in perms}
            continue

        role_data = raw.get(role)
        if not isinstance(role_data, dict):
            continue

        for perm in perms:
            if perm in role_data:
                normalized[role][perm] = bool(role_data.get(perm))

    return normalized


def _load_permission_matrix(db: Session) -> Dict[str, Dict[str, bool]]:
    matrix = _default_permission_matrix()
    perms = _permission_keys()
    rows = db.query(RolePermission).all()
    if not rows:
        return matrix

    for row in rows:
        role = _norm(row.role).lower()
        perm = _norm(row.permission)
        if role not in ALL_ROLES or perm not in perms:
            continue
        if role == Role.ADMIN.value:
            matrix[role][perm] = True
            continue
        matrix[role][perm] = bool(row.allowed)
    return matrix


def _default_scope_rules() -> Dict[str, Dict[str, List[str]]]:
    # لیست خالی یعنی محدودیت اعمال نشود (دسترسی به همه)
    return {
        role: {
            "projects": [],
            "disciplines": [],
        }
        for role in ALL_ROLES
    }


def _normalize_scope_values(values: Any, *, upper: bool = True) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    for raw in values:
        value = _norm(raw)
        if not value:
            continue
        normalized.append(value.upper() if upper else value)
    return sorted(set(normalized))


def _normalize_scope_rules(raw: Any) -> Dict[str, Dict[str, List[str]]]:
    normalized = _default_scope_rules()
    if not isinstance(raw, dict):
        return normalized

    for role in ALL_ROLES:
        if role == Role.ADMIN.value:
            # ادمین همیشه unrestricted است
            normalized[role] = {"projects": [], "disciplines": []}
            continue

        role_data = raw.get(role)
        if not isinstance(role_data, dict):
            continue

        normalized[role]["projects"] = _normalize_scope_values(role_data.get("projects"))
        normalized[role]["disciplines"] = _normalize_scope_values(role_data.get("disciplines"))

    return normalized


def _load_scope_rules(db: Session) -> Dict[str, Dict[str, List[str]]]:
    normalized = _default_scope_rules()
    role_projects = db.query(RoleProjectScope.role, RoleProjectScope.project_code).all()
    for role, project_code in role_projects:
        role_key = _norm(role).lower()
        if role_key in normalized and project_code:
            normalized[role_key]["projects"].append(_upper(project_code))

    role_disciplines = db.query(RoleDisciplineScope.role, RoleDisciplineScope.discipline_code).all()
    for role, discipline_code in role_disciplines:
        role_key = _norm(role).lower()
        if role_key in normalized and discipline_code:
            normalized[role_key]["disciplines"].append(_upper(discipline_code))

    for role in ALL_ROLES:
        normalized[role]["projects"] = sorted(set(normalized[role]["projects"]))
        normalized[role]["disciplines"] = sorted(set(normalized[role]["disciplines"]))
    return normalized


def _default_user_scope_rules() -> Dict[str, Dict[str, List[str]]]:
    return {}


def _normalize_user_scope_rules(raw: Any) -> Dict[str, Dict[str, List[str]]]:
    if not isinstance(raw, dict):
        return _default_user_scope_rules()

    normalized: Dict[str, Dict[str, List[str]]] = {}
    for user_id, values in raw.items():
        key = _norm(user_id)
        if not key:
            continue
        if not isinstance(values, dict):
            continue
        normalized[key] = {
            "projects": _normalize_scope_values(values.get("projects")),
            "disciplines": _normalize_scope_values(values.get("disciplines")),
        }
    return normalized


def _load_user_scope_rules(db: Session) -> Dict[str, Dict[str, List[str]]]:
    normalized: Dict[str, Dict[str, List[str]]] = {}

    project_rows = db.query(UserProjectScope.user_id, UserProjectScope.project_code).all()
    for user_id, project_code in project_rows:
        key = str(user_id)
        normalized.setdefault(key, {"projects": [], "disciplines": []})
        if project_code:
            normalized[key]["projects"].append(_upper(project_code))

    discipline_rows = db.query(UserDisciplineScope.user_id, UserDisciplineScope.discipline_code).all()
    for user_id, discipline_code in discipline_rows:
        key = str(user_id)
        normalized.setdefault(key, {"projects": [], "disciplines": []})
        if discipline_code:
            normalized[key]["disciplines"].append(_upper(discipline_code))

    for key, values in normalized.items():
        values["projects"] = sorted(set(values["projects"]))
        values["disciplines"] = sorted(set(values["disciplines"]))
    return normalized


# -----------------------------
# Endpoints
# -----------------------------

@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """
    نمایش آمار کلی سیستم
    """
    return {
        "ok": True,
        "app": settings.APP_NAME,
        "db": {"url": settings.DATABASE_URL},
        "counts": {
            "projects": _count(db, Project),
            "phases": _count(db, Phase),
            "disciplines": _count(db, Discipline),
            "packages": _count(db, Package),
            "levels": _count(db, Level),
            "blocks": _count(db, Block),
            "mdr_categories": _count(db, MdrCategory),
            "settings_kv": _count(db, SettingsKV),
            "statuses": _count(db, DocStatus),
            "role_permissions": _count(db, RolePermission),
            "role_project_scopes": _count(db, RoleProjectScope),
            "role_discipline_scopes": _count(db, RoleDisciplineScope),
            "user_project_scopes": _count(db, UserProjectScope),
            "user_discipline_scopes": _count(db, UserDisciplineScope),
            "settings_audit_logs": _count(db, SettingsAuditLog),
            "correspondences": _count(db, Correspondence),
            "correspondence_actions": _count(db, CorrespondenceAction),
            "correspondence_attachments": _count(db, CorrespondenceAttachment),
        },
    }

@router.post("/seed")
def seed_all(db: Session = Depends(get_db)):
    """
    فراخوانی سرویس Seed برای خواندن اکسل Master Data و آپدیت دیتابیس.
    همراه با لاگ‌گیری دقیق خطاها.
    """
    print(f"[INFO] Seeding triggered via API")
    
    try:
        # بررسی وجود فایل قبل از اجرا
        excel_path = settings.BASE_DIR / "data_sources" / "master_data.xlsx"
        if not excel_path.exists():
            print(f"[ERROR] Excel file not found at: {excel_path}")
            return {"ok": False, "message": f"File not found: {excel_path}"}

        stats = seed_service.seed_from_excel(db)
        
        if "error" in stats:
             print(f"[ERROR] Seed service returned error: {stats['error']}")
             return {"ok": False, "message": stats["error"]}
             
        db.commit()
        print("[SUCCESS] Database seeded successfully.")
        return {"ok": True, "stats": stats, "source": "Excel"}
        
    except Exception as e:
        db.rollback()
        print("!!!!!!!!!!!!!! SEEDING ERROR !!!!!!!!!!!!!!")
        traceback.print_exc()  # چاپ کامل متن خطا در ترمینال
        raise HTTPException(status_code=500, detail=f"Seeding failed: {str(e)}")


# --- Projects ---
@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.code).all()
    return {"ok": True, "items": [
        {
            "id": p.id, "code": p.code, "project_code": p.code,
            "project_name": p.name_e or p.name_p,
            "root_path": p.root_path, "is_active": p.is_active,
            "docnum_template": p.docnum_template
        } for p in projects
    ]}

@router.post("/projects/upsert")
def upsert_project(
    payload: ProjectIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _upper(payload.code)
    if not code: raise HTTPException(status_code=400, detail="code is required")
    proj = db.query(Project).filter(Project.code == code).first()
    before = _as_dict(proj, ["code", "name_e", "name_p", "root_path", "is_active", "docnum_template"])
    pname = _norm(payload.project_name) or _norm(payload.name_e) or _norm(payload.name_p)
    if proj:
        if pname: proj.name_e = pname
        proj.root_path = _norm(payload.root_path) or proj.root_path
        if payload.is_active is not None: proj.is_active = payload.is_active
        proj.docnum_template = _norm(payload.docnum_template) or proj.docnum_template
    else:
        proj = Project(code=code, name_e=pname, root_path=_norm(payload.root_path),
                       is_active=payload.is_active if payload.is_active is not None else True,
                       docnum_template=_norm(payload.docnum_template) or "{PROJECT}-{MDR}{PKG}-{BLK}{LVL}")
        db.add(proj)
    _audit_log(
        db,
        actor=current_user,
        action="project.upsert",
        target_type="project",
        target_key=code,
        before=before,
        after=_as_dict(proj, ["code", "name_e", "name_p", "root_path", "is_active", "docnum_template"]),
    )
    db.commit()
    return {"ok": True, "message": "Project upserted", "code": code}

@router.post("/projects/delete")
def delete_project(
    payload: ProjectDeleteIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _upper(payload.code)
    row = db.query(Project).filter(Project.code == code).first()
    if not row:
        return {"ok": True, "message": "Project not found (noop)"}
    before = _as_dict(row, ["code", "name_e", "name_p", "root_path", "is_active", "docnum_template"])

    if payload.hard_delete:
        try:
            _audit_log(
                db,
                actor=current_user,
                action="project.delete.hard",
                target_type="project",
                target_key=code,
                before=before,
                after=None,
            )
            db.delete(row)
            db.commit()
            return {"ok": True, "message": "Project deleted", "code": code}
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"Project {code} is in use and cannot be hard deleted.",
            )

    row.is_active = False
    _audit_log(
        db,
        actor=current_user,
        action="project.delete.soft",
        target_type="project",
        target_key=code,
        before=before,
        after=_as_dict(row, ["code", "name_e", "name_p", "root_path", "is_active", "docnum_template"]),
    )
    db.commit()
    return {"ok": True, "message": "Project disabled", "code": code}


# --- Blocks ---
@router.get("/blocks")
def list_blocks(project_code: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    q = db.query(Block)
    if project_code: q = q.filter(Block.project_code == _upper(project_code))
    rows = q.order_by(Block.project_code, Block.sort_order, Block.code).all()
    return {"ok": True, "items": [
        {"id": b.id, "project_code": b.project_code, "code": b.code, "name_e": b.name_e, "name_p": b.name_p,
         "sort_order": b.sort_order, "is_active": b.is_active} for b in rows
    ]}

@router.post("/blocks/upsert")
def upsert_block(
    payload: BlockIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    pcode = _upper(payload.project_code)
    bcode = _upper(payload.code)
    proj = db.query(Project).filter(Project.code == pcode).first()
    if not proj: raise HTTPException(status_code=400, detail=f"Project {pcode} not found")
    blk = db.query(Block).filter(Block.project_code == pcode, Block.code == bcode).first()
    before = _as_dict(blk, ["project_code", "code", "name_e", "name_p", "sort_order", "is_active"])
    if blk:
        blk.name_e = _norm(payload.name_e) or blk.name_e
        blk.name_p = _norm(payload.name_p) or blk.name_p
        blk.sort_order = payload.sort_order
        blk.is_active = payload.is_active
    else:
        blk = Block(project_code=pcode, code=bcode, name_e=_norm(payload.name_e) or bcode,
                    name_p=_norm(payload.name_p), sort_order=payload.sort_order, is_active=payload.is_active)
        db.add(blk)
    _audit_log(
        db,
        actor=current_user,
        action="block.upsert",
        target_type="block",
        target_key=f"{pcode}:{bcode}",
        before=before,
        after=_as_dict(blk, ["project_code", "code", "name_e", "name_p", "sort_order", "is_active"]),
    )
    db.commit()
    return {"ok": True, "message": "Block upserted", "project_code": pcode, "code": bcode}

@router.post("/blocks/delete")
def delete_block(
    payload: BlockDeleteIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    pcode = _upper(payload.project_code)
    bcode = _upper(payload.code)
    blk = db.query(Block).filter(Block.project_code == pcode, Block.code == bcode).first()
    if not blk: return {"ok": True, "message": "Block not found (noop)"}
    before = _as_dict(blk, ["project_code", "code", "name_e", "name_p", "sort_order", "is_active"])
    if payload.hard_delete: db.delete(blk)
    else: blk.is_active = False
    _audit_log(
        db,
        actor=current_user,
        action="block.delete.hard" if payload.hard_delete else "block.delete.soft",
        target_type="block",
        target_key=f"{pcode}:{bcode}",
        before=before,
        after=None if payload.hard_delete else _as_dict(blk, ["project_code", "code", "name_e", "name_p", "sort_order", "is_active"]),
    )
    db.commit()
    return {"ok": True, "message": "Block deleted" if payload.hard_delete else "Block disabled"}


# --- MDR Categories ---
@router.get("/mdr-categories")
def list_mdr_categories(db: Session = Depends(get_db)):
    rows = db.query(MdrCategory).order_by(MdrCategory.sort_order, MdrCategory.code).all()
    return {"ok": True, "items": [
        {"code": r.code, "name_e": r.name_e, "name_p": r.name_p, "folder_name": r.folder_name,
         "sort_order": r.sort_order, "is_active": r.is_active} for r in rows
    ]}

@router.post("/mdr-categories/upsert")
def upsert_mdr_category(
    payload: MdrCategoryIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _upper(payload.code)
    if not code: raise HTTPException(status_code=400, detail="code is required")
    row = db.query(MdrCategory).filter(MdrCategory.code == code).first()
    before = _as_dict(row, ["code", "name_e", "name_p", "folder_name", "sort_order", "is_active"])
    if row:
        row.name_e = _norm(payload.name_e) or row.name_e
        row.name_p = _norm(payload.name_p) or row.name_p
        row.folder_name = _norm(payload.folder_name) or row.folder_name
        row.sort_order = payload.sort_order
        row.is_active = payload.is_active
    else:
        row = MdrCategory(code=code, name_e=_norm(payload.name_e), name_p=_norm(payload.name_p),
                          folder_name=_norm(payload.folder_name) or _norm(payload.name_e),
                          sort_order=payload.sort_order, is_active=payload.is_active)
        db.add(row)
    _audit_log(
        db,
        actor=current_user,
        action="mdr_category.upsert",
        target_type="mdr_category",
        target_key=code,
        before=before,
        after=_as_dict(row, ["code", "name_e", "name_p", "folder_name", "sort_order", "is_active"]),
    )
    db.commit()
    return {"ok": True, "message": "MDR Category upserted", "code": code}

@router.post("/mdr-categories/delete")
def delete_mdr_category(
    payload: MdrCategoryDeleteIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _upper(payload.code)
    row = db.query(MdrCategory).filter(MdrCategory.code == code).first()
    if not row: return {"ok": True, "message": "MDR Category not found (noop)"}
    before = _as_dict(row, ["code", "name_e", "name_p", "folder_name", "sort_order", "is_active"])
    if payload.hard_delete: db.delete(row)
    else: row.is_active = False
    _audit_log(
        db,
        actor=current_user,
        action="mdr_category.delete.hard" if payload.hard_delete else "mdr_category.delete.soft",
        target_type="mdr_category",
        target_key=code,
        before=before,
        after=None if payload.hard_delete else _as_dict(row, ["code", "name_e", "name_p", "folder_name", "sort_order", "is_active"]),
    )
    db.commit()
    return {"ok": True, "message": "MDR Category deleted" if payload.hard_delete else "MDR Category disabled"}


# --- Phases ---
@router.get("/phases")
def list_phases_settings(db: Session = Depends(get_db)):
    phases = db.query(Phase).order_by(Phase.ph_code).all()
    return {"ok": True, "items": [{"ph_code": p.ph_code, "name_e": p.name_e, "name_p": p.name_p} for p in phases]}

@router.post("/phases/upsert")
def upsert_phase_settings(
    payload: PhaseIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _upper(payload.ph_code)
    ph = db.query(Phase).filter(Phase.ph_code == code).first()
    before = _as_dict(ph, ["ph_code", "name_e", "name_p"])
    if ph: ph.name_e = payload.name_e; ph.name_p = payload.name_p
    else:
        ph = Phase(ph_code=code, name_e=payload.name_e, name_p=payload.name_p)
        db.add(ph)
    _audit_log(
        db,
        actor=current_user,
        action="phase.upsert",
        target_type="phase",
        target_key=code,
        before=before,
        after=_as_dict(ph, ["ph_code", "name_e", "name_p"]),
    )
    db.commit()
    return {"ok": True, "message": "Phase upserted"}

@router.post("/phases/delete")
def delete_phase_settings(
    payload: PhaseDeleteIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _upper(payload.ph_code)
    row = db.query(Phase).filter(Phase.ph_code == code).first()
    if not row:
        return {"ok": True, "message": "Phase not found (noop)"}
    before = _as_dict(row, ["ph_code", "name_e", "name_p"])
    try:
        _audit_log(
            db,
            actor=current_user,
            action="phase.delete.hard",
            target_type="phase",
            target_key=code,
            before=before,
            after=None,
        )
        db.delete(row)
        db.commit()
        return {"ok": True, "message": "Phase deleted", "ph_code": code}
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Phase {code} is in use by documents and cannot be deleted.",
        )


# --- Disciplines ---
@router.get("/disciplines")
def list_disciplines_settings(db: Session = Depends(get_db)):
    discs = db.query(Discipline).order_by(Discipline.code).all()
    return {"ok": True, "items": [{"code": d.code, "discipline_code": d.code, "name_e": d.name_e, "name_p": d.name_p} for d in discs]}

@router.post("/disciplines/upsert")
def upsert_discipline_settings(
    payload: DisciplineIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _upper(payload.code)
    disc = db.query(Discipline).filter(Discipline.code == code).first()
    before = _as_dict(disc, ["code", "name_e", "name_p"])
    if disc:
        disc.name_e = payload.name_e
        if payload.name_p: disc.name_p = payload.name_p
    else:
        disc = Discipline(code=code, name_e=payload.name_e, name_p=payload.name_p)
        db.add(disc)
    _audit_log(
        db,
        actor=current_user,
        action="discipline.upsert",
        target_type="discipline",
        target_key=code,
        before=before,
        after=_as_dict(disc, ["code", "name_e", "name_p"]),
    )
    db.commit()
    return {"ok": True, "message": "Discipline upserted"}

@router.post("/disciplines/delete")
def delete_discipline_settings(
    payload: DisciplineDeleteIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _upper(payload.code)
    row = db.query(Discipline).filter(Discipline.code == code).first()
    if not row:
        return {"ok": True, "message": "Discipline not found (noop)"}
    before = _as_dict(row, ["code", "name_e", "name_p"])
    try:
        _audit_log(
            db,
            actor=current_user,
            action="discipline.delete.hard",
            target_type="discipline",
            target_key=code,
            before=before,
            after=None,
        )
        db.delete(row)
        db.commit()
        return {"ok": True, "message": "Discipline deleted", "code": code}
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Discipline {code} is in use and cannot be deleted.",
        )


# --- Packages ---
@router.get("/packages")
def list_packages_settings(discipline_code: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    q = db.query(Package)
    if discipline_code:
        q = q.filter(Package.discipline_code == _upper(discipline_code))
    rows = q.order_by(Package.discipline_code, Package.package_code).all()
    return {"ok": True, "items": [
        {
            "discipline_code": r.discipline_code,
            "package_code": r.package_code,
            "name_e": r.name_e,
            "name_p": r.name_p,
        }
        for r in rows
    ]}

@router.post("/packages/upsert")
def upsert_package_settings(
    payload: PackageIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    dcode = _upper(payload.discipline_code)
    pcode = _upper(payload.package_code)

    disc = db.query(Discipline).filter(Discipline.code == dcode).first()
    if not disc:
        raise HTTPException(status_code=400, detail=f"Discipline {dcode} not found")

    row = db.query(Package).filter(Package.discipline_code == dcode, Package.package_code == pcode).first()
    before = _as_dict(row, ["discipline_code", "package_code", "name_e", "name_p"])
    if row:
        row.name_e = _norm(payload.name_e)
        row.name_p = _norm(payload.name_p) or row.name_p
    else:
        row = Package(
            discipline_code=dcode,
            package_code=pcode,
            name_e=_norm(payload.name_e),
            name_p=_norm(payload.name_p),
        )
        db.add(row)
    _audit_log(
        db,
        actor=current_user,
        action="package.upsert",
        target_type="package",
        target_key=f"{dcode}:{pcode}",
        before=before,
        after=_as_dict(row, ["discipline_code", "package_code", "name_e", "name_p"]),
    )
    db.commit()
    return {"ok": True, "message": "Package upserted", "discipline_code": dcode, "package_code": pcode}

@router.post("/packages/delete")
def delete_package_settings(
    payload: PackageDeleteIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    dcode = _upper(payload.discipline_code)
    pcode = _upper(payload.package_code)
    row = db.query(Package).filter(Package.discipline_code == dcode, Package.package_code == pcode).first()
    if not row:
        return {"ok": True, "message": "Package not found (noop)"}
    before = _as_dict(row, ["discipline_code", "package_code", "name_e", "name_p"])
    try:
        _audit_log(
            db,
            actor=current_user,
            action="package.delete.hard",
            target_type="package",
            target_key=f"{dcode}:{pcode}",
            before=before,
            after=None,
        )
        db.delete(row)
        db.commit()
        return {"ok": True, "message": "Package deleted", "discipline_code": dcode, "package_code": pcode}
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Package {pcode} in discipline {dcode} is in use and cannot be deleted.",
        )


# --- Levels ---
@router.get("/levels")
def list_levels_settings(db: Session = Depends(get_db)):
    levels = db.query(Level).order_by(Level.sort_order, Level.code).all()
    return {"ok": True, "items": [{"code": l.code, "name_e": l.name_e, "name_p": l.name_p, "sort_order": l.sort_order} for l in levels]}

@router.post("/levels/upsert")
def upsert_level_settings(
    payload: LevelIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _norm(payload.code)
    lvl = db.query(Level).filter(Level.code == code).first()
    before = _as_dict(lvl, ["code", "name_e", "name_p", "sort_order"])
    if lvl:
        if payload.name_e: lvl.name_e = payload.name_e
        if payload.name_p: lvl.name_p = payload.name_p
        lvl.sort_order = payload.sort_order
    else:
        lvl = Level(code=code, name_e=payload.name_e or code, name_p=payload.name_p, sort_order=payload.sort_order)
        db.add(lvl)
    _audit_log(
        db,
        actor=current_user,
        action="level.upsert",
        target_type="level",
        target_key=code,
        before=before,
        after=_as_dict(lvl, ["code", "name_e", "name_p", "sort_order"]),
    )
    db.commit()
    return {"ok": True, "message": "Level upserted"}

@router.post("/levels/delete")
def delete_level_settings(
    payload: LevelDeleteIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _norm(payload.code)
    row = db.query(Level).filter(Level.code == code).first()
    if not row:
        return {"ok": True, "message": "Level not found (noop)"}
    before = _as_dict(row, ["code", "name_e", "name_p", "sort_order"])
    try:
        _audit_log(
            db,
            actor=current_user,
            action="level.delete.hard",
            target_type="level",
            target_key=code,
            before=before,
            after=None,
        )
        db.delete(row)
        db.commit()
        return {"ok": True, "message": "Level deleted", "code": code}
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Level {code} is in use by documents and cannot be deleted.",
        )


# --- Statuses (✅ ADDED) ---
@router.get("/statuses")
def list_statuses_settings(db: Session = Depends(get_db)):
    statuses = db.query(DocStatus).order_by(DocStatus.sort_order).all()
    return {"ok": True, "items": [{"code": s.code, "name": s.name, "description": s.description, "sort_order": s.sort_order} for s in statuses]}

@router.post("/statuses/upsert")
def upsert_status_settings(
    payload: DocStatusIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _upper(payload.code)
    st = db.query(DocStatus).filter(DocStatus.code == code).first()
    before = _as_dict(st, ["code", "name", "description", "sort_order"])
    if st:
        st.name = payload.name
        st.description = payload.description
        st.sort_order = payload.sort_order
    else:
        st = DocStatus(code=code, name=payload.name, description=payload.description, sort_order=payload.sort_order)
        db.add(st)
    _audit_log(
        db,
        actor=current_user,
        action="status.upsert",
        target_type="status",
        target_key=code,
        before=before,
        after=_as_dict(st, ["code", "name", "description", "sort_order"]),
    )
    db.commit()
    return {"ok": True, "message": "Status upserted"}

@router.post("/statuses/delete")
def delete_status_settings(
    payload: DocStatusDeleteIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    code = _upper(payload.code)
    row = db.query(DocStatus).filter(DocStatus.code == code).first()
    if not row:
        return {"ok": True, "message": "Status not found (noop)"}
    before = _as_dict(row, ["code", "name", "description", "sort_order"])
    _audit_log(
        db,
        actor=current_user,
        action="status.delete.hard",
        target_type="status",
        target_key=code,
        before=before,
        after=None,
    )
    db.delete(row)
    db.commit()
    return {"ok": True, "message": "Status deleted", "code": code}


# --- KV ---
@router.get("/kv")
def kv_list(
    include_legacy: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return {"ok": True, "items": _kv_get_all(db, include_legacy=include_legacy)}

@router.post("/kv/set")
def kv_set(
    payload: KvIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    key = _norm(payload.key)
    if not _is_allowed_kv_write_key(key):
        raise HTTPException(
            status_code=403,
            detail=(
                "KV key is not allowed. "
                f"Allowed prefixes: {', '.join(KV_ALLOWED_WRITE_PREFIXES)}"
            ),
        )

    before_row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
    before_val = before_row.value if before_row else None

    _kv_set(db, key, payload.value)
    _audit_log(
        db,
        actor=current_user,
        action="kv.set",
        target_type="kv",
        target_key=key,
        before={"value": before_val},
        after={"value": payload.value},
    )
    db.commit()
    return {"ok": True, "message": "Setting saved"}


@router.get("/storage-paths")
def get_storage_paths(db: Session = Depends(get_db)):
    return {
        "ok": True,
        "mdr_storage_path": _kv_get_value(db, STORAGE_PATH_MDR_KEY, DEFAULT_MDR_STORAGE_PATH),
        "correspondence_storage_path": _kv_get_value(
            db,
            STORAGE_PATH_CORRESPONDENCE_KEY,
            DEFAULT_CORRESPONDENCE_STORAGE_PATH,
        ),
    }


@router.post("/storage-paths")
def save_storage_paths(
    payload: StoragePathsIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    mdr_storage_path = _norm(payload.mdr_storage_path)
    correspondence_storage_path = _norm(payload.correspondence_storage_path)
    if not mdr_storage_path or not correspondence_storage_path:
        raise HTTPException(status_code=422, detail="Storage paths cannot be empty")

    before = {
        "mdr_storage_path": _kv_get_value(db, STORAGE_PATH_MDR_KEY, DEFAULT_MDR_STORAGE_PATH),
        "correspondence_storage_path": _kv_get_value(
            db,
            STORAGE_PATH_CORRESPONDENCE_KEY,
            DEFAULT_CORRESPONDENCE_STORAGE_PATH,
        ),
    }
    after = {
        "mdr_storage_path": mdr_storage_path,
        "correspondence_storage_path": correspondence_storage_path,
    }

    _kv_set(db, STORAGE_PATH_MDR_KEY, mdr_storage_path)
    _kv_set(db, STORAGE_PATH_CORRESPONDENCE_KEY, correspondence_storage_path)
    _audit_log(
        db,
        actor=current_user,
        action="storage_paths.update",
        target_type="storage_paths",
        target_key=None,
        before=before,
        after=after,
    )
    db.commit()
    return {"ok": True, "message": "Storage paths updated", **after}


@router.get("/permissions/matrix")
def get_permissions_matrix(db: Session = Depends(get_db)):
    matrix = _load_permission_matrix(db)
    return {
        "ok": True,
        "roles": list(ALL_ROLES),
        "permissions": _permission_keys(),
        "matrix": matrix,
    }


@router.post("/permissions/matrix")
def save_permissions_matrix(
    payload: PermissionMatrixIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    before = _load_permission_matrix(db)
    matrix = _normalize_permission_matrix(payload.matrix)
    perms = _permission_keys()
    db.query(RolePermission).delete(synchronize_session=False)
    for role in ALL_ROLES:
        for perm in perms:
            db.add(
                RolePermission(
                    role=role,
                    permission=perm,
                    allowed=True if role == Role.ADMIN.value else bool(matrix[role][perm]),
                )
            )
    _audit_log(
        db,
        actor=current_user,
        action="permissions.matrix.save",
        target_type="permissions_matrix",
        target_key=None,
        before=before,
        after=matrix,
    )
    db.commit()
    return {"ok": True, "message": "Permissions matrix saved", "matrix": matrix}


@router.get("/permissions/scope")
def get_permissions_scope(db: Session = Depends(get_db)):
    scope = _load_scope_rules(db)
    projects = [
        {"code": p.code, "name": p.name_e or p.name_p or p.code}
        for p in db.query(Project).filter(Project.is_active == True).order_by(Project.code).all()
    ]
    disciplines = [
        {"code": d.code, "name": d.name_e or d.name_p or d.code}
        for d in db.query(Discipline).order_by(Discipline.code).all()
    ]
    return {
        "ok": True,
        "roles": list(ALL_ROLES),
        "scope": scope,
        "projects": projects,
        "disciplines": disciplines,
    }


@router.post("/permissions/scope")
def save_permissions_scope(
    payload: PermissionScopeIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    before = _load_scope_rules(db)
    scope = _normalize_scope_rules(payload.scope)
    project_codes = {code for (code,) in db.query(Project.code).all()}
    discipline_codes = {code for (code,) in db.query(Discipline.code).all()}

    db.query(RoleProjectScope).delete(synchronize_session=False)
    db.query(RoleDisciplineScope).delete(synchronize_session=False)

    for role in ALL_ROLES:
        for code in scope.get(role, {}).get("projects", []):
            if code in project_codes:
                db.add(RoleProjectScope(role=role, project_code=code))
        for code in scope.get(role, {}).get("disciplines", []):
            if code in discipline_codes:
                db.add(RoleDisciplineScope(role=role, discipline_code=code))
    _audit_log(
        db,
        actor=current_user,
        action="permissions.scope.save",
        target_type="role_scope",
        target_key=None,
        before=before,
        after=scope,
    )
    db.commit()
    return {"ok": True, "message": "Permission scope saved", "scope": scope}


@router.get("/permissions/user-scope")
def get_permissions_user_scope(db: Session = Depends(get_db)):
    scope = _load_user_scope_rules(db)
    users = db.query(DbUser).order_by(DbUser.id).all()
    return {
        "ok": True,
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "is_active": u.is_active,
            }
            for u in users
        ],
        "scope": scope,
    }


@router.post("/permissions/user-scope/upsert")
def upsert_permissions_user_scope(
    payload: UserPermissionScopeIn,
    db: Session = Depends(get_db),
    current_user: DbUser = Depends(allow_admin),
):
    user = db.query(DbUser).filter(DbUser.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    before_all_scope = _load_user_scope_rules(db)
    before_user_scope = before_all_scope.get(str(payload.user_id), {"projects": [], "disciplines": []})
    normalized_projects = _normalize_scope_values(payload.projects)
    normalized_disciplines = _normalize_scope_values(payload.disciplines)
    project_codes = {code for (code,) in db.query(Project.code).all()}
    discipline_codes = {code for (code,) in db.query(Discipline.code).all()}

    db.query(UserProjectScope).filter(UserProjectScope.user_id == payload.user_id).delete(synchronize_session=False)
    db.query(UserDisciplineScope).filter(UserDisciplineScope.user_id == payload.user_id).delete(synchronize_session=False)

    saved_projects: List[str] = []
    for code in normalized_projects:
        if code in project_codes:
            db.add(UserProjectScope(user_id=payload.user_id, project_code=code))
            saved_projects.append(code)

    saved_disciplines: List[str] = []
    for code in normalized_disciplines:
        if code in discipline_codes:
            db.add(UserDisciplineScope(user_id=payload.user_id, discipline_code=code))
            saved_disciplines.append(code)

    after_user_scope = {
        "projects": sorted(set(saved_projects)),
        "disciplines": sorted(set(saved_disciplines)),
    }
    _audit_log(
        db,
        actor=current_user,
        action="permissions.user_scope.upsert",
        target_type="user_scope",
        target_key=str(payload.user_id),
        before=before_user_scope,
        after=after_user_scope,
    )
    db.commit()
    return {
        "ok": True,
        "message": "User scope saved",
        "user_id": payload.user_id,
        "scope": after_user_scope,
    }


@router.get("/permissions/access-report")
def permissions_access_report(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=False),
    include_denied: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    project = _upper(project_code)
    discipline = _upper(discipline_code)
    if not project and not discipline:
        raise HTTPException(
            status_code=400,
            detail="At least one filter is required: project_code or discipline_code",
        )
    items = _build_access_report_items(
        db,
        project_code=project,
        discipline_code=discipline,
        include_inactive=include_inactive,
        include_denied=include_denied,
    )

    return {
        "ok": True,
        "filters": {"project_code": project or None, "discipline_code": discipline or None},
        "count": len(items),
        "items": items,
    }


@router.get("/permissions/access-report.csv")
def permissions_access_report_csv(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=False),
    include_denied: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    project = _upper(project_code)
    discipline = _upper(discipline_code)
    if not project and not discipline:
        raise HTTPException(
            status_code=400,
            detail="At least one filter is required: project_code or discipline_code",
        )

    items = _build_access_report_items(
        db,
        project_code=project,
        discipline_code=discipline,
        include_inactive=include_inactive,
        include_denied=include_denied,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "user_id",
            "email",
            "full_name",
            "role",
            "is_active",
            "has_access",
            "project_allowed",
            "discipline_allowed",
            "projects_restricted",
            "disciplines_restricted",
            "effective_projects",
            "effective_disciplines",
            "project_filter",
            "discipline_filter",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.get("user_id"),
                item.get("email"),
                item.get("full_name"),
                item.get("role"),
                item.get("is_active"),
                item.get("has_access"),
                item.get("project_allowed"),
                item.get("discipline_allowed"),
                item.get("projects_restricted"),
                item.get("disciplines_restricted"),
                ",".join(item.get("effective_projects", [])),
                ",".join(item.get("effective_disciplines", [])),
                project or "",
                discipline or "",
            ]
        )

    filename = f"permissions_access_report_{project or 'ALL'}_{discipline or 'ALL'}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/permissions/user-access/{user_id}")
def permissions_user_access_report(
    user_id: int,
    include_catalog: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    user = db.query(DbUser).filter(DbUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = normalize_role(user.role)
    role_scope = _load_scope_rules(db).get(role, {"projects": [], "disciplines": []})
    user_scope = _load_user_scope_rules(db).get(str(user_id), {"projects": [], "disciplines": []})
    projects, projects_restricted = _effective_scope_values(
        role_scope.get("projects", []),
        user_scope.get("projects", []),
    )
    disciplines, disciplines_restricted = _effective_scope_values(
        role_scope.get("disciplines", []),
        user_scope.get("disciplines", []),
    )

    payload: Dict[str, Any] = {
        "ok": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": role,
            "is_active": user.is_active,
        },
        "role_scope": role_scope,
        "user_scope": user_scope,
        "effective_scope": {
            "projects": projects,
            "disciplines": disciplines,
            "projects_restricted": projects_restricted,
            "disciplines_restricted": disciplines_restricted,
        },
    }

    if include_catalog:
        all_projects = {
            code: (name_e or name_p or code)
            for code, name_e, name_p in db.query(Project.code, Project.name_e, Project.name_p).all()
        }
        all_disciplines = {
            code: (name_e or name_p or code)
            for code, name_e, name_p in db.query(Discipline.code, Discipline.name_e, Discipline.name_p).all()
        }
        payload["effective_scope_catalog"] = {
            "projects": [{"code": c, "name": all_projects.get(c, c)} for c in projects],
            "disciplines": [{"code": c, "name": all_disciplines.get(c, c)} for c in disciplines],
        }

    return payload


@router.get("/audit-logs")
@router.get("/permissions/audit-logs")
def permissions_audit_logs(
    limit: Optional[int] = Query(default=None, ge=1, le=1000),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    offset: Optional[int] = Query(default=None, ge=0),
    action: Optional[str] = Query(default=None),
    target_type: Optional[str] = Query(default=None),
    target_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(SettingsAuditLog)
    if action:
        q = q.filter(SettingsAuditLog.action == _norm(action))
    if target_type:
        q = q.filter(SettingsAuditLog.target_type == _norm(target_type))
    if target_key:
        q = q.filter(SettingsAuditLog.target_key == _norm(target_key))

    effective_page_size = int(limit) if limit is not None else int(page_size)
    effective_offset = int(offset) if offset is not None else (int(page) - 1) * effective_page_size
    total = q.count()
    rows = (
        q.order_by(SettingsAuditLog.created_at.desc())
        .offset(effective_offset)
        .limit(effective_page_size)
        .all()
    )

    total_pages = max(1, (total + effective_page_size - 1) // effective_page_size)
    current_page = (effective_offset // effective_page_size) + 1
    return {
        "ok": True,
        "pagination": {
            "total": total,
            "page": current_page,
            "page_size": effective_page_size,
            "offset": effective_offset,
            "count": len(rows),
            "total_pages": total_pages,
        },
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "target_type": row.target_type,
                "target_key": row.target_key,
                "actor_user_id": row.actor_user_id,
                "actor_email": row.actor_email,
                "actor_name": row.actor_name,
                "before_json": row.before_json,
                "after_json": row.after_json,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }
