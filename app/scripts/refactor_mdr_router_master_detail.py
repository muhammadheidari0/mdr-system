from __future__ import annotations

import re
from pathlib import Path


def _detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _must_replace(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Pattern not found for {label}:\n{old!r}")
    return text.replace(old, new, 1)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    target = repo_root / "app" / "api" / "v1" / "routers" / "mdr.py"
    if not target.exists():
        raise RuntimeError(f"mdr.py not found at: {target}")

    original = target.read_text(encoding="utf-8")
    nl = _detect_newline(original)

    backup = target.with_suffix(target.suffix + ".bak_before_master_detail")
    backup.write_text(original, encoding="utf-8")

    text = original

    # Imports
    text = _must_replace(
        text,
        f"from sqlalchemy.orm import Session{nl}",
        f"from sqlalchemy.orm import Session, aliased{nl}",
        label="import_sqlalchemy_orm",
    )
    text = _must_replace(
        text,
        f"from sqlalchemy import or_{nl}",
        f"from sqlalchemy import or_, func{nl}",
        label="import_sqlalchemy",
    )
    text = _must_replace(
        text,
        f"from app.db.models import MdrDocument, Project, Phase, Block, MdrCategory, Discipline, Package{nl}",
        f"from app.db.models import MdrDocument, DocumentRevision, Project, Phase, Block, MdrCategory, Discipline, Package{nl}",
        label="import_models",
    )

    # /mdr/submit: remove revision/status on MdrDocument
    text = _must_replace(
        text,
        f"        revision=\"00\", status=\"Created\", notes=f\"Folder: {{folder_path}}\"{nl}",
        f"        notes=f\"Folder: {{folder_path}}\"{nl}",
        label="submit_new_doc_fields",
    )

    text = _must_replace(
        text,
        f"    db.add(new_doc){nl}    db.commit(){nl}    return {{\"ok\": True, \"docNumber\": doc_num, \"serial\": serial_str, \"folderPath\": folder_path}}{nl}",
        (
            f"    db.add(new_doc){nl}"
            f"    db.flush(){nl}"
            f"{nl}"
            f"    rev = DocumentRevision(document_id=new_doc.id, revision=\"00\", status=\"Created\", notes=f\"Folder: {{folder_path}}\"){nl}"
            f"    db.add(rev){nl}"
            f"    db.commit(){nl}"
            f"    return {{\"ok\": True, \"docNumber\": doc_num, \"serial\": serial_str, \"folderPath\": folder_path}}{nl}"
        ),
        label="submit_commit_block",
    )

    # /mdr/bulk-register: remove revision/status on MdrDocument and create DocumentRevision
    text = _must_replace(
        text,
        f"                    revision=\"00\", status=\"IFA\", doc_title_p=final_subject,{nl}",
        f"                    doc_title_p=final_subject,{nl}",
        label="bulk_new_doc_fields",
    )

    text = _must_replace(
        text,
        f"                db.add(new_doc){nl}                db.commit(){nl}",
        (
            f"                db.add(new_doc){nl}"
            f"                db.flush(){nl}"
            f"                db.add(DocumentRevision(document_id=new_doc.id, revision=\"00\", status=\"IFA\", notes=f\"Path: {{folder_path_str}}\")){nl}"
            f"                db.commit(){nl}"
        ),
        label="bulk_commit_block",
    )

    # /mdr/search: replace entire endpoint block from decorator to EOF (robust vs spacing differences)
    new_search_block = (
        f"@router.get(\"/search\"){nl}"
        f"def search_documents({nl}"
        f"    project_code: Optional[str] = None, mdr_code: Optional[str] = None,{nl}"
        f"    doc: Optional[str] = None, subject: Optional[str] = None,{nl}"
        f"    status: Optional[str] = None, revision: Optional[str] = None,{nl}"
        f"    page: int = 1, size: int = 20, sort_by: str = \"created_at\", sort_dir: str = \"desc\",{nl}"
        f"    db: Session = Depends(get_db){nl}"
        f"): {nl}"
        f"    latest_subq = ({nl}"
        f"        db.query({nl}"
        f"            DocumentRevision.document_id.label(\"document_id\"),{nl}"
        f"            func.max(DocumentRevision.created_at).label(\"max_created_at\"),{nl}"
        f"        ){nl}"
        f"        .group_by(DocumentRevision.document_id){nl}"
        f"        .subquery(){nl}"
        f"    ){nl}"
        f"{nl}"
        f"    Rev = aliased(DocumentRevision){nl}"
        f"    q = ({nl}"
        f"        db.query(MdrDocument, Rev){nl}"
        f"        .outerjoin(latest_subq, latest_subq.c.document_id == MdrDocument.id){nl}"
        f"        .outerjoin(Rev, (Rev.document_id == MdrDocument.id) & (Rev.created_at == latest_subq.c.max_created_at)){nl}"
        f"    ){nl}"
        f"    if project_code: q = q.filter(MdrDocument.project_code == project_code){nl}"
        f"    if mdr_code: q = q.filter(MdrDocument.mdr_code == mdr_code){nl}"
        f"    if revision: q = q.filter(Rev.revision == revision){nl}"
        f"    if status: q = q.filter(Rev.status.ilike(f\"%{{status.strip()}}%\")){nl}"
        f"    if doc: q = q.filter(MdrDocument.doc_number.ilike(f\"%{{doc.strip().replace(' ', '%')}}%\")){nl}"
        f"    if subject: q = q.filter(or_(MdrDocument.doc_title_e.ilike(f\"%{{subject}}%\"), MdrDocument.doc_title_p.ilike(f\"%{{subject}}%\"))){nl}"
        f"{nl}"
        f"    sort_col = getattr(MdrDocument, sort_by, MdrDocument.created_at){nl}"
        f"    q = q.order_by(sort_col.asc() if sort_dir == \"asc\" else sort_col.desc()){nl}"
        f"{nl}"
        f"    total = q.count(){nl}"
        f"    rows = q.offset((page - 1) * size).limit(size).all(){nl}"
        f"{nl}"
        f"    return {{{nl}"
        f"        \"ok\": True, \"total\": total, \"page\": page, \"size\": size, \"pages\": (total + size - 1) // size,{nl}"
        f"        \"items\": [{{{nl}"
        f"            \"id\": d.id, \"doc_number\": d.doc_number, \"project_code\": d.project_code,{nl}"
        f"            \"status\": (r.status if r else None), \"revision\": (r.revision if r else None),{nl}"
        f"            \"doc_title_p\": d.doc_title_p, \"doc_title_e\": d.doc_title_e,{nl}"
        f"            \"created_at\": d.created_at.isoformat() if d.created_at else None{nl}"
        f"        }} for (d, r) in rows]{nl}"
        f"    }}{nl}"
    )

    search_pattern = re.compile(r'@router\.get\("/search"\)[\s\S]*\Z')
    if not search_pattern.search(text):
        raise RuntimeError("Pattern not found for search endpoint block")
    text = search_pattern.sub(new_search_block, text, count=1)

    target.write_text(text, encoding="utf-8")
    print("OK: mdr.py updated")
    print("Backup:", backup)


if __name__ == "__main__":
    main()
