# app/api/v1/routers/lookup.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.api.dependencies import User, allow_admin, get_db
# ✅ مدل‌های جدید (MdrCategory, Block) اضافه شدند
from app.db.models import (
    Project, 
    Phase, 
    Discipline, 
    Package, 
    Level, 
    MdrCategory, 
    Block
)

router = APIRouter(prefix="/lookup", tags=["Lookup"])


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def ok(data: Any) -> dict:
    return {"ok": True, "data": data}

def _norm(s: Optional[str]) -> str:
    return (s or "").strip()

def _upper(s: Optional[str]) -> str:
    return _norm(s).upper()


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
    user: User = Depends(allow_admin),
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
    user: User = Depends(allow_admin),
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
    user: User = Depends(allow_admin),
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
    package_code: str,
    name_e: str,
    name_p: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(allow_admin),
):
    dcode = _upper(discipline_code)
    pcode = _upper(package_code)

    disc = db.query(Discipline).filter(Discipline.code == dcode).first()
    if not disc:
        raise HTTPException(status_code=400, detail=f"Discipline {dcode} not found")

    pkg = db.query(Package).filter(Package.discipline_code == dcode, Package.package_code == pcode).first()
    if pkg:
        pkg.name_e = _norm(name_e)
        if name_p: pkg.name_p = _norm(name_p)
    else:
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
    user: User = Depends(allow_admin),
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
# Dictionary Endpoint (Updated)
# ------------------------------------------------------------
@router.get("/dictionary")
def dictionary(db: Session = Depends(get_db)):
    """
    همه اطلاعات پایه را یکجا برمی‌گرداند.
    لیست‌های MDR و Block اکنون از دیتابیس خوانده می‌شوند.
    """
    return ok({
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
        # ✅ دریافت دینامیک بلاک‌ها
        "blocks": [
            {"code": r.code, "name_e": r.name_e, "project_code": r.project_code}
            for r in db.query(Block).filter(Block.is_active == True).all()
        ],
        # ✅ دریافت دینامیک دسته‌های MDR
        "mdr_categories": [
            {"code": r.code, "name": r.name_e, "letter": r.code, "name_p": r.name_p}
            for r in db.query(MdrCategory).filter(MdrCategory.is_active == True).order_by(MdrCategory.sort_order).all()
        ]
    })
