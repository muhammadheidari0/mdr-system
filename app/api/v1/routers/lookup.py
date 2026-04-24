# app/api/v1/routers/lookup.py
from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.api.dependencies import User, get_db, require_permission
# ✅ مدل‌های جدید (MdrCategory, Block) اضافه شدند
from app.db.models import (
    Project, 
    Phase, 
    Discipline, 
    Package, 
    Level, 
    Organization,
    MdrCategory, 
    Block
)

router = APIRouter(prefix="/lookup", tags=["Lookup"], dependencies=[Depends(require_permission("lookup:read"))])


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def ok(data: Any) -> dict:
    return {"ok": True, "data": data}

def _norm(s: Optional[str]) -> str:
    return (s or "").strip()

def _upper(s: Optional[str]) -> str:
    return _norm(s).upper()


_PKG_SEQ_RE = re.compile(r"(\d{1,3})$")


def _extract_package_sequence(code: Optional[str], discipline_code: Optional[str] = None) -> Optional[int]:
    raw = _upper(code)
    if not raw:
        return None
    dcode = _upper(discipline_code)
    candidate = raw
    if dcode and candidate.startswith(dcode):
        candidate = candidate[len(dcode):]

    if candidate.isdigit():
        seq = int(candidate)
    else:
        match = _PKG_SEQ_RE.search(candidate)
        if not match:
            return None
        seq = int(match.group(1))

    if seq < 1 or seq > 99:
        return None
    return seq


def _normalize_package_code(code: Optional[str], discipline_code: Optional[str] = None) -> str:
    seq = _extract_package_sequence(code, discipline_code)
    if seq is None:
        return _upper(code)
    return f"{seq:02d}"


def _next_package_code(db: Session, discipline_code: str) -> str:
    dcode = _upper(discipline_code)
    used: set[int] = set()
    rows = db.query(Package.package_code).filter(Package.discipline_code == dcode).all()
    for (pkg_code,) in rows:
        seq = _extract_package_sequence(pkg_code, dcode)
        if seq is not None:
            used.add(seq)
    for seq in range(1, 100):
        if seq not in used:
            return f"{seq:02d}"
    raise HTTPException(status_code=400, detail=f"No available package code for discipline {dcode}")


# ------------------------------------------------------------
# Projects
# ------------------------------------------------------------
@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).filter(Project.is_active == True).order_by(Project.code).all()
    return ok([
        {
            "id": p.id,
            "code": p.code,
            "project_code": p.code,
            "project_name": p.name_e or p.name_p,
            "root_path": p.root_path,
            "is_active": p.is_active,
            "docnum_template": p.docnum_template,
        }
        for p in projects
    ])

@router.post("/projects")
def upsert_project(
    code: str,
    name_e: Optional[str] = None,
    name_p: Optional[str] = None,
    root_path: Optional[str] = None,
    is_active: bool = True,
    docnum_template: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("lookup:manage")),
):
    code = _norm(code)
    if not code:
        raise HTTPException(status_code=400, detail="code is required")

    proj = db.query(Project).filter(Project.code == code).first()

    if proj:
        if name_e: proj.name_e = _norm(name_e)
        if name_p: proj.name_p = _norm(name_p)
        if root_path: proj.root_path = _norm(root_path)
        if docnum_template: proj.docnum_template = _norm(docnum_template)
        proj.is_active = is_active
    else:
        proj = Project(
            code=code,
            name_e=_norm(name_e),
            name_p=_norm(name_p),
            root_path=_norm(root_path),
            is_active=is_active,
            docnum_template=_norm(docnum_template)
        )
        db.add(proj)

    db.commit()
    db.refresh(proj)
    return ok({"id": proj.id, "code": proj.code})


# ------------------------------------------------------------
# Phases
# ------------------------------------------------------------
@router.get("/phases")
def list_phases(db: Session = Depends(get_db)):
    phases = db.query(Phase).order_by(Phase.ph_code).all()
    return ok([
        {"ph_code": p.ph_code, "name_e": p.name_e, "name_p": p.name_p}
        for p in phases
    ])

@router.post("/phases")
def upsert_phase(
    ph_code: str,
    name_e: str,
    name_p: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("lookup:manage")),
):
    ph_code = _upper(ph_code)
    if not ph_code:
        raise HTTPException(status_code=400, detail="ph_code is required")

    phase = db.query(Phase).filter(Phase.ph_code == ph_code).first()
    if phase:
        phase.name_e = _norm(name_e)
        if name_p: phase.name_p = _norm(name_p)
    else:
        db.add(Phase(ph_code=ph_code, name_e=_norm(name_e), name_p=_norm(name_p)))
    db.commit()
    return ok({"ph_code": ph_code})


# ------------------------------------------------------------
# Disciplines
# ------------------------------------------------------------
@router.get("/disciplines")
def list_disciplines(db: Session = Depends(get_db)):
    discs = db.query(Discipline).order_by(Discipline.code).all()
    return ok([
        {"code": d.code, "discipline_code": d.code, "name_e": d.name_e, "name_p": d.name_p}
        for d in discs
    ])

@router.post("/disciplines")
def upsert_discipline(
    code: str,
    name_e: str,
    name_p: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("lookup:manage")),
):
    dcode = _upper(code)
    disc = db.query(Discipline).filter(Discipline.code == dcode).first()
    if disc:
        disc.name_e = _norm(name_e)
        if name_p: disc.name_p = _norm(name_p)
    else:
        db.add(Discipline(code=dcode, name_e=_norm(name_e), name_p=_norm(name_p)))
    db.commit()
    return ok({"code": dcode})


# ------------------------------------------------------------
# Packages
# ------------------------------------------------------------
@router.get("/packages")
def list_packages(
    discipline_code: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Package)
    if discipline_code:
        query = query.filter(Package.discipline_code == _upper(discipline_code))
    
    if q:
        search = f"%{_norm(q)}%"
        query = query.filter(or_(
            Package.package_code.like(search),
            Package.name_e.like(search),
            Package.name_p.like(search)
        ))
    
    rows = query.order_by(Package.discipline_code, Package.package_code).all()
    return ok([
        {"discipline_code": r.discipline_code, "package_code": r.package_code, "name_e": r.name_e, "name_p": r.name_p}
        for r in rows
    ])

@router.post("/packages")
def upsert_package(
    discipline_code: str,
    name_e: str,
    package_code: Optional[str] = None,
    name_p: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("lookup:manage")),
):
    dcode = _upper(discipline_code)
    raw_pcode = _upper(package_code)

    disc = db.query(Discipline).filter(Discipline.code == dcode).first()
    if not disc:
        raise HTTPException(status_code=400, detail=f"Discipline {dcode} not found")

    normalized_input_code = _normalize_package_code(raw_pcode, dcode)
    candidate_codes: list[str] = []
    if raw_pcode:
        candidate_codes.append(raw_pcode)
    if normalized_input_code and normalized_input_code not in candidate_codes:
        candidate_codes.append(normalized_input_code)

    pkg = None
    for code in candidate_codes:
        pkg = db.query(Package).filter(Package.discipline_code == dcode, Package.package_code == code).first()
        if pkg:
            break

    if pkg:
        pcode = pkg.package_code
        pkg.name_e = _norm(name_e)
        if name_p: pkg.name_p = _norm(name_p)
    else:
        pcode = _next_package_code(db, dcode)
        db.add(Package(discipline_code=dcode, package_code=pcode, name_e=_norm(name_e), name_p=_norm(name_p)))
    
    db.commit()
    return ok({"discipline_code": dcode, "package_code": pcode})


# ------------------------------------------------------------
# Levels
# ------------------------------------------------------------
@router.get("/levels")
def list_levels(db: Session = Depends(get_db)):
    levels = db.query(Level).order_by(Level.sort_order, Level.code).all()
    return ok([
        {"code": l.code, "name_e": l.name_e, "name_p": l.name_p, "sort_order": l.sort_order}
        for l in levels
    ])

@router.post("/levels")
def upsert_level(
    code: str,
    sort_order: int = 0,
    name_e: Optional[str] = None,
    name_p: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("lookup:manage")),
):
    code = _norm(code)
    lvl = db.query(Level).filter(Level.code == code).first()
    if lvl:
        if name_e: lvl.name_e = _norm(name_e)
        if name_p: lvl.name_p = _norm(name_p)
        lvl.sort_order = sort_order
    else:
        db.add(Level(code=code, name_e=_norm(name_e) or code, name_p=_norm(name_p), sort_order=sort_order))
    db.commit()
    return ok({"code": code})


# ------------------------------------------------------------
# ✅ NEW: MDR Categories (Dynamic)
# ------------------------------------------------------------
@router.get("/mdr-categories")
def list_mdr_categories(db: Session = Depends(get_db)):
    cats = db.query(MdrCategory).filter(MdrCategory.is_active == True).order_by(MdrCategory.sort_order).all()
    return ok([
        {"code": c.code, "name_e": c.name_e, "name_p": c.name_p, "folder_name": c.folder_name}
        for c in cats
    ])


# ------------------------------------------------------------
# ✅ NEW: Blocks (Dynamic)
# ------------------------------------------------------------
@router.get("/blocks")
def list_blocks(project_code: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Block).filter(Block.is_active == True)
    if project_code:
        q = q.filter(Block.project_code == project_code)
    blocks = q.order_by(Block.sort_order).all()
    return ok([
        {"code": b.code, "name_e": b.name_e, "project_code": b.project_code}
        for b in blocks
    ])


# ------------------------------------------------------------
# Dictionary Endpoint (Updated) – with in-process TTL cache
# ------------------------------------------------------------
import time as _time

_dict_cache: dict[str, Any] = {"data": None, "expires": 0.0}
_DICT_TTL_SECONDS = 300  # 5 minutes


@router.get("/dictionary")
def dictionary(db: Session = Depends(get_db)):
    """
    همه اطلاعات پایه را یکجا برمی‌گرداند.
    لیست‌های MDR و Block اکنون از دیتابیس خوانده می‌شوند.
    نتایج به مدت ۵ دقیقه در حافظه کش می‌شوند.
    """
    now = _time.monotonic()
    if _dict_cache["data"] is not None and now < _dict_cache["expires"]:
        return _dict_cache["data"]

    result = ok({
        "projects": [
            {"code": r.code, "project_name": r.name_e or r.name_p}
            for r in db.query(Project).filter(Project.is_active == True).all()
        ],
        "phases": [
            {"ph_code": r.ph_code, "name_e": r.name_e, "name_p": r.name_p}
            for r in db.query(Phase).all()
        ],
        "disciplines": [
            {"code": r.code, "name_e": r.name_e, "name_p": r.name_p}
            for r in db.query(Discipline).all()
        ],
        "packages": [
            {
                "discipline_code": r.discipline_code,
                "package_code": r.package_code,
                "name_e": r.name_e,
                "name_p": r.name_p,
            }
            for r in db.query(Package).all()
        ],
        "levels": [
            {"code": r.code, "name_e": r.name_e, "name_p": r.name_p}
            for r in db.query(Level).order_by(Level.sort_order).all()
        ],
        "blocks": [
            {"code": r.code, "name_e": r.name_e, "project_code": r.project_code}
            for r in db.query(Block).filter(Block.is_active == True).all()
        ],
        "mdr_categories": [
            {"code": r.code, "name": r.name_e, "letter": r.code, "name_p": r.name_p}
            for r in db.query(MdrCategory).filter(MdrCategory.is_active == True).order_by(MdrCategory.sort_order).all()
        ],
        "organizations": [
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "org_type": r.org_type,
                "parent_id": r.parent_id,
                "is_active": r.is_active,
            }
            for r in db.query(Organization).filter(Organization.is_active == True).all()
        ],
    })

    _dict_cache["data"] = result
    _dict_cache["expires"] = now + _DICT_TTL_SECONDS
    return result
