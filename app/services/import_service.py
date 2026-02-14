from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Tuple

import pandas as pd
import requests
from sqlalchemy.orm import Session

from app.db.models import (
    Discipline,
    Level,
    MdrCategory,
    MdrDocument,
    Package,
    Phase,
    Project,
)

_INVALID_PLACEHOLDERS = {"X", "GN", "00", "G", "GEN", "undefined"}
_INVALID_PLACEHOLDERS_UPPER = {str(x).strip().upper() for x in _INVALID_PLACEHOLDERS}


def _normalize_lookup_token(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9\u0600-\u06FF]+", "", str(value or "").upper())


def _is_invalid_placeholder(value: str | None) -> bool:
    return str(value or "").strip().upper() in _INVALID_PLACEHOLDERS_UPPER


class LookupCache:
    """In-memory lookup cache to avoid repeated SELECTs per row."""

    def __init__(self, db: Session):
        self.db = db
        self.projects = {row[0] for row in db.query(Project.code).all()}
        self.phases = set()
        self.disciplines = set()
        self.levels = set()
        self.mdr_categories = set()

        self.phase_alias_to_code: Dict[str, str] = {}
        for code, name in db.query(Phase.ph_code, Phase.name_e).all():
            if not code:
                continue
            c = str(code).strip().upper()
            self.phases.add(c)
            self.phase_alias_to_code[_normalize_lookup_token(c)] = c
            if name:
                self.phase_alias_to_code[_normalize_lookup_token(name)] = c

        self.discipline_alias_to_code: Dict[str, str] = {}
        for code, name in db.query(Discipline.code, Discipline.name_e).all():
            if not code:
                continue
            c = str(code).strip().upper()
            self.disciplines.add(c)
            self.discipline_alias_to_code[_normalize_lookup_token(c)] = c
            if name:
                self.discipline_alias_to_code[_normalize_lookup_token(name)] = c

        self.level_alias_to_code: Dict[str, str] = {}
        self.level_name_p_by_code: Dict[str, str] = {}
        for code, name_e, name_p in db.query(Level.code, Level.name_e, Level.name_p).all():
            if not code:
                continue
            c = str(code).strip().upper()
            self.levels.add(c)
            self.level_alias_to_code[_normalize_lookup_token(c)] = c
            if name_e:
                self.level_alias_to_code[_normalize_lookup_token(name_e)] = c
            if name_p:
                self.level_alias_to_code[_normalize_lookup_token(name_p)] = c
                self.level_name_p_by_code[c] = str(name_p).strip()

        self.mdr_alias_to_code: Dict[str, str] = {}
        for code, name in db.query(MdrCategory.code, MdrCategory.name_e).all():
            if not code:
                continue
            c = str(code).strip().upper()
            self.mdr_categories.add(c)
            self.mdr_alias_to_code[_normalize_lookup_token(c)] = c
            if name:
                self.mdr_alias_to_code[_normalize_lookup_token(name)] = c

        self.packages = set()
        self.package_names: Dict[tuple[str, str], tuple[str, str]] = {}
        self.package_alias_to_code_by_disc: Dict[tuple[str, str], str] = {}
        for disc, pkg, name_e, name_p in db.query(
            Package.discipline_code,
            Package.package_code,
            Package.name_e,
            Package.name_p,
        ).all():
            if not disc or not pkg:
                continue
            disc_code = str(disc).strip().upper()
            pkg_code = str(pkg).strip().upper()
            key = (disc_code, pkg_code)
            self.packages.add(key)
            self.package_names[key] = (name_e or pkg_code, name_p or pkg_code)

            alias_values = {pkg_code, name_e, name_p}
            for alias in alias_values:
                t = _normalize_lookup_token(alias)
                if t:
                    self.package_alias_to_code_by_disc[(disc_code, t)] = pkg_code

    def ensure(self, project: str, phase: str, disc: str, pkg: str, level: str, mdr: str) -> None:
        if project and project not in self.projects:
            self.db.add(
                Project(
                    code=project,
                    name_e=f"Project {project}",
                    docnum_template="{PROJECT}-{MDR}{PHASE}{PKG}{SERIAL}-{BLOCK}{LEVEL}",
                )
            )
            self.projects.add(project)

        if phase and phase not in self.phases:
            self.db.add(Phase(ph_code=phase, name_e=f"Phase {phase}"))
            self.phases.add(phase)

        if disc and disc not in self.disciplines:
            self.db.add(Discipline(code=disc, name_e=f"Discipline {disc}"))
            self.disciplines.add(disc)

        if level and level not in self.levels:
            self.db.add(Level(code=level, name_e=f"Level {level}"))
            self.levels.add(level)

        if mdr and mdr not in self.mdr_categories:
            self.db.add(MdrCategory(code=mdr, name_e=f"Category {mdr}"))
            self.mdr_categories.add(mdr)

        if pkg and disc:
            key = (disc, pkg)
            if key not in self.packages:
                self.db.add(
                    Package(
                        package_code=pkg,
                        discipline_code=disc,
                        name_e=f"Package {pkg}",
                    )
                )
                self.packages.add(key)
                self.package_names[key] = (pkg, pkg)

    def get_package_names(self, disc: str, pkg: str) -> tuple[str, str]:
        disc_code = str(disc or "").strip().upper()
        pkg_code = str(pkg or "").strip().upper()
        if not disc_code or not pkg_code:
            base = pkg_code or "00"
            return base, base
        return self.package_names.get((disc_code, pkg_code), (pkg_code, pkg_code))

    def get_level_name_p(self, level_code: str) -> str:
        code = str(level_code or "").strip().upper()
        if not code:
            return ""
        return self.level_name_p_by_code.get(code, code)

    def _resolve_with_alias_map(
        self,
        raw_value: str | None,
        alias_map: Dict[str, str],
        direct_codes: set[str],
        fallback: str,
    ) -> str:
        raw = str(raw_value or "").strip()
        if raw:
            t = _normalize_lookup_token(raw)
            if t and t in alias_map:
                return alias_map[t]
            direct = raw.upper()
            if direct in direct_codes:
                return direct
        return str(fallback or "").strip().upper()

    def resolve_phase_code(self, raw_value: str | None, fallback: str = "X") -> str:
        return self._resolve_with_alias_map(raw_value, self.phase_alias_to_code, self.phases, fallback or "X") or "X"

    def resolve_discipline_code(self, raw_value: str | None, fallback: str = "GN") -> str:
        return self._resolve_with_alias_map(
            raw_value, self.discipline_alias_to_code, self.disciplines, fallback or "GN"
        ) or "GN"

    def resolve_level_code(self, raw_value: str | None, fallback: str = "GEN") -> str:
        return self._resolve_with_alias_map(raw_value, self.level_alias_to_code, self.levels, fallback or "GEN") or "GEN"

    def resolve_mdr_code(self, raw_value: str | None, fallback: str = "E") -> str:
        return self._resolve_with_alias_map(raw_value, self.mdr_alias_to_code, self.mdr_categories, fallback or "E") or "E"

    def resolve_package_code(
        self,
        discipline_code: str,
        raw_value: str | None,
        fallback: str = "00",
    ) -> str:
        disc = str(discipline_code or "").strip().upper()
        raw = str(raw_value or "").strip()
        if disc and raw:
            token = _normalize_lookup_token(raw)
            if token:
                hit = self.package_alias_to_code_by_disc.get((disc, token))
                if hit:
                    return hit
            direct_pkg = raw.upper()
            if (disc, direct_pkg) in self.packages:
                return direct_pkg
        return str(fallback or "00").strip().upper() or "00"


class PrefixSerialCache:
    """Cache serial calculations per prefix to avoid repeated LIKE scans."""

    def __init__(self, db: Session):
        self.db = db
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _load_prefix(self, base_prefix: str) -> Dict[str, Any]:
        rows = (
            self.db.query(MdrDocument.doc_number, MdrDocument.subject)
            .filter(MdrDocument.doc_number.like(f"{base_prefix}%"))
            .all()
        )

        max_serial = 0
        subject_to_serial: Dict[str, str] = {}
        existing_doc_numbers = set()

        for doc_number, subject in rows:
            existing_doc_numbers.add(doc_number)
            serial_str = _extract_serial_from_doc_number(doc_number)
            if serial_str is None:
                continue
            serial_int = int(serial_str)
            if serial_int > max_serial:
                max_serial = serial_int

            normalized = _normalize_subject(subject)
            if normalized and normalized not in subject_to_serial:
                subject_to_serial[normalized] = serial_str

        payload = {
            "max_serial": max_serial,
            "subject_to_serial": subject_to_serial,
            "existing_doc_numbers": existing_doc_numbers,
        }
        self._cache[base_prefix] = payload
        return payload

    def get_existing_doc_numbers(self, base_prefix: str) -> set[str]:
        data = self._cache.get(base_prefix) or self._load_prefix(base_prefix)
        return data["existing_doc_numbers"]

    def resolve_serial(self, base_prefix: str, subject: str) -> str:
        data = self._cache.get(base_prefix) or self._load_prefix(base_prefix)
        normalized = _normalize_subject(subject)
        if normalized and normalized in data["subject_to_serial"]:
            return data["subject_to_serial"][normalized]

        data["max_serial"] += 1
        serial_str = f"{data['max_serial']:02d}"
        if normalized:
            data["subject_to_serial"][normalized] = serial_str
        return serial_str

    def mark_doc_number(self, base_prefix: str, doc_number: str) -> None:
        data = self._cache.get(base_prefix) or self._load_prefix(base_prefix)
        data["existing_doc_numbers"].add(doc_number)


class DuplicateMetaKeyCache:
    """Cache existing documents by metadata key:
    Project + MDR + Phase + Discipline + Package + Block + Level + Subject(normalized)
    """

    def __init__(self, db: Session):
        self.db = db
        self._cache: Dict[Tuple[str, str, str, str, str, str, str], Dict[str, str]] = {}

    def _load_base(
        self,
        project: str,
        mdr: str,
        phase: str,
        discipline: str,
        package: str,
        block: str,
        level: str,
    ) -> Dict[str, str]:
        rows = (
            self.db.query(MdrDocument.doc_number, MdrDocument.subject)
            .filter(MdrDocument.project_code == project)
            .filter(MdrDocument.mdr_code == mdr)
            .filter(MdrDocument.phase_code == phase)
            .filter(MdrDocument.discipline_code == discipline)
            .filter(MdrDocument.package_code == package)
            .filter(MdrDocument.block == block)
            .filter(MdrDocument.level_code == level)
            .all()
        )
        by_subject: Dict[str, str] = {}
        for doc_number, subject in rows:
            key = _normalize_subject(subject)
            if key and key not in by_subject:
                by_subject[key] = doc_number
        return by_subject

    def _get_base_map(
        self,
        project: str,
        mdr: str,
        phase: str,
        discipline: str,
        package: str,
        block: str,
        level: str,
    ) -> Dict[str, str]:
        base = (project, mdr, phase, discipline, package, block, level)
        if base not in self._cache:
            self._cache[base] = self._load_base(*base)
        return self._cache[base]

    def find_existing_doc(
        self,
        project: str,
        mdr: str,
        phase: str,
        discipline: str,
        package: str,
        block: str,
        level: str,
        subject: str,
    ) -> str | None:
        subject_key = _normalize_subject(subject)
        if not subject_key:
            return None
        by_subject = self._get_base_map(project, mdr, phase, discipline, package, block, level)
        return by_subject.get(subject_key)

    def mark_new_doc(
        self,
        project: str,
        mdr: str,
        phase: str,
        discipline: str,
        package: str,
        block: str,
        level: str,
        subject: str,
        doc_number: str,
    ) -> None:
        subject_key = _normalize_subject(subject)
        if not subject_key:
            return
        by_subject = self._get_base_map(project, mdr, phase, discipline, package, block, level)
        by_subject[subject_key] = doc_number


# ---------------------------------------------------------
# 1. Extract Metadata from Code
# ---------------------------------------------------------
def _extract_metadata_from_code(code: str) -> dict:
    meta = {
        "project": "T202",
        "mdr": "E",
        "phase": "X",
        "disc": "GN",
        "pkg": "00",
        "block": "G",
        "level": "GEN",
    }

    if not code or len(code) < 10 or "-" not in code:
        return meta

    try:
        parts = code.split("-")
        if parts[0]:
            meta["project"] = parts[0]

        if len(parts) >= 2:
            middle = parts[1]
            if len(middle) >= 4:
                meta["mdr"] = middle[0]
                meta["phase"] = middle[1]
                serial_match = re.search(r"(\d{2})$", middle)
                serial_len = 2 if serial_match else 0
                core_pkg = middle[2 : len(middle) - serial_len]

                if core_pkg:
                    meta["pkg"] = core_pkg
                    meta["disc"] = core_pkg[:2] if len(core_pkg) >= 2 else "GN"

        if len(parts) >= 3:
            suffix = parts[2]
            if len(suffix) >= 2:
                meta["block"] = suffix[0]
                meta["level"] = suffix[1:]
    except Exception:
        pass
    return meta


def _normalize_subject(subject: str | None) -> str:
    return re.sub(r"[^a-zA-Z0-9\u0600-\u06FF]", "", subject or "").lower()


def _extract_serial_from_doc_number(doc_number: str) -> str | None:
    parts = (doc_number or "").split("-")
    if len(parts) < 2:
        return None
    match = re.search(r"(\d{2})$", parts[1])
    return match.group(1) if match else None


def _build_full_titles(
    pkg_name_e: str | None,
    pkg_name_p: str | None,
    pkg_code: str | None,
    block: str | None,
    level: str | None,
    level_name_p: str | None,
    subject: str | None,
) -> tuple[str, str]:
    block_code = str(block or "").strip().upper() or "G"
    level_code = str(level or "").strip().upper() or "GEN"
    is_general = level_code == "GEN"
    safe_subject = str(subject or "").strip()

    base_e = str(pkg_name_e or pkg_code or "00").strip() or "00"
    base_p = str(pkg_name_p or pkg_code or base_e).strip() or base_e

    title_e = base_e
    if not is_general:
        title_e = f"{title_e}-{block_code}{level_code}"
    if safe_subject:
        title_e = f"{title_e} - {safe_subject}"

    if is_general:
        title_p = base_p
    else:
        location_name_p = str(level_name_p or level_code).strip() or level_code
        title_p = f"{location_name_p}-{block_code}-{base_p}"
    if safe_subject:
        title_p = f"{title_p}-{safe_subject}"
    return title_e, title_p


def _prefetch_existing_explicit_codes(db: Session, lines: List[str]) -> set[str]:
    explicit_codes = set()
    for line in lines:
        row = line.rstrip("\r")
        if not row.strip():
            continue
        parts = row.split("\t")
        new_format = len(parts) >= 11
        raw_code_idx = 10 if new_format else 8
        raw_code = parts[raw_code_idx].strip().upper() if len(parts) > raw_code_idx else ""
        if raw_code and len(raw_code) >= 10 and "-" in raw_code:
            explicit_codes.add(raw_code)

    if not explicit_codes:
        return set()

    return {
        row[0]
        for row in db.query(MdrDocument.doc_number)
        .filter(MdrDocument.doc_number.in_(explicit_codes))
        .all()
    }


# ---------------------------------------------------------
# 2. Excel & Google Sheet Parser
# ---------------------------------------------------------
def parse_excel_or_link(file_content: bytes = None, url: str = None) -> List[dict]:
    all_results = []
    target_sheets = ["engineering", "procurement", "construction", "mdr", "sheet1", "data"]

    try:
        excel_file = None
        if file_content:
            excel_file = io.BytesIO(file_content)
        elif url:
            if "docs.google.com" in url:
                clean_url = url.split("?")[0]
                if "/edit" in clean_url:
                    url = clean_url.split("/edit")[0] + "/export?format=xlsx"
                elif "/view" in clean_url:
                    url = clean_url.split("/view")[0] + "/export?format=xlsx"

            resp = requests.get(url, timeout=45)
            resp.raise_for_status()
            excel_file = io.BytesIO(resp.content)

        if excel_file:
            try:
                xls = pd.ExcelFile(excel_file)
                for name in xls.sheet_names:
                    if any(target in name.lower() for target in target_sheets):
                        try:
                            df_preview = pd.read_excel(xls, sheet_name=name, header=None, nrows=5)
                            header_idx = 0
                            for idx, row in df_preview.iterrows():
                                row_str = " ".join([str(x) for x in row.values]).lower()
                                if "document number" in row_str or "project code" in row_str:
                                    header_idx = idx
                                    break

                            df = pd.read_excel(xls, sheet_name=name, header=header_idx).fillna("")
                            all_results.extend(_process_dataframe(df, name))
                        except Exception:
                            continue
            except Exception:
                if file_content:
                    try:
                        excel_file.seek(0)
                        df = pd.read_csv(excel_file, header=0, encoding="utf-8-sig").fillna("")
                        all_results.extend(_process_dataframe(df, "CSV"))
                    except Exception:
                        pass
    except Exception:
        return []
    return all_results


def _process_dataframe(df: pd.DataFrame, source_name: str) -> List[dict]:
    results = []
    df.columns = [str(c).strip() for c in df.columns]
    normalized_to_col: Dict[str, str] = {}
    for col in df.columns:
        key = _normalize_lookup_token(col)
        if key and key not in normalized_to_col:
            normalized_to_col[key] = col

    col_map = {
        "doc_number": ["Document Number", "Doc No", "Doc Number"],
        "title_e": ["Document Title/E", "Title (E)", "Document Title"],
        "title_p": ["Document Title/P", "Title (P)"],
        "subject_e": ["Subject/E"],
        "subject_p": ["Subject/P"],
        "subject_gen": ["Subject"],
        "project": ["Project code", "Project", "Project Code"],
        "mdr": ["MDR", "MDR code", "MDR_Code"],
        "phase": ["Phase"],
        "disc": ["Discipline"],
        "pkg": ["Package_Name_E", "Package", "Pkg"],
        "block": ["Block", "Blk"],
        "level": ["Location", "Level", "Lvl"],
    }

    resolved_cols: Dict[str, str] = {}
    for logical_key, aliases in col_map.items():
        found = ""
        for alias in aliases:
            hit = normalized_to_col.get(_normalize_lookup_token(alias))
            if hit:
                found = hit
                break
        resolved_cols[logical_key] = found

    def get_val(row, logical_key: str):
        col_name = resolved_cols.get(logical_key) or ""
        if col_name and col_name in row:
            val = row[col_name]
            if val is not None and str(val).strip():
                return str(val).strip()
        return ""

    for _, row in df.iterrows():
        doc_num = get_val(row, "doc_number").upper()
        sub_e = get_val(row, "subject_e")
        sub_p = get_val(row, "subject_p")
        sub_gen = get_val(row, "subject_gen")
        final_subject = sub_p if sub_p else (sub_e if sub_e else sub_gen)

        if not doc_num or len(doc_num) < 3:
            continue

        parsed = _extract_metadata_from_code(doc_num)
        project_val = (parsed.get("project") or get_val(row, "project") or "").upper()
        mdr_val = (parsed.get("mdr") or get_val(row, "mdr") or "").upper()
        phase_val = (parsed.get("phase") or get_val(row, "phase") or "").upper()
        disc_val = (parsed.get("disc") or get_val(row, "disc") or "").upper()
        pkg_val = (parsed.get("pkg") or get_val(row, "pkg") or "").upper()
        block_val = (parsed.get("block") or get_val(row, "block") or "").upper()
        level_val = (parsed.get("level") or get_val(row, "level") or "").upper()

        results.append(
            {
                "doc_number": doc_num,
                "title_e": get_val(row, "title_e"),
                "title_p": get_val(row, "title_p"),
                "subject": final_subject,
                "project": project_val,
                "mdr": mdr_val,
                "phase": phase_val,
                "disc": disc_val,
                "pkg": pkg_val,
                "block": block_val,
                "level": level_val,
                "source": source_name,
            }
        )
    return results


# ---------------------------------------------------------
# 3. Main Process Logic (Optimized)
# ---------------------------------------------------------
def process_bulk_text(db: Session, text_data: str) -> Dict[str, Any]:
    if not text_data:
        return {"ok": False, "message": "No data found."}

    results = {"total": 0, "success": 0, "failed": 0, "details": []}
    lines = text_data.split("\n")

    lookup_cache = LookupCache(db)
    serial_cache = PrefixSerialCache(db)
    duplicate_meta_cache = DuplicateMetaKeyCache(db)
    existing_doc_numbers = _prefetch_existing_explicit_codes(db, lines)
    batch_doc_numbers = set()
    batch_meta_keys: Dict[Tuple[str, str, str, str, str, str, str, str], str] = {}
    new_documents: List[MdrDocument] = []

    for line in lines:
        row = line.rstrip("\r")
        if not row.strip():
            continue
        results["total"] += 1
        parts = row.split("\t")

        new_format = len(parts) >= 11
        idx_offset = 2 if new_format else 0
        raw_code_idx = 10 if new_format else 8
        raw_code = parts[raw_code_idx].strip().upper() if len(parts) > raw_code_idx else ""
        parsed = _extract_metadata_from_code(raw_code)

        def read_new_field(offset: int) -> str:
            src_idx = idx_offset + offset
            val = parts[src_idx].strip() if len(parts) > src_idx else ""
            return "" if _is_invalid_placeholder(val) else val

        phase_raw = read_new_field(0)
        disc_raw = read_new_field(1)
        pkg_raw = read_new_field(2)
        block_raw = read_new_field(3)
        level_raw = read_new_field(4)
        subject_val = read_new_field(5)

        project_raw = parts[0].strip() if (new_format and len(parts) > 0) else ""
        mdr_raw = parts[1].strip() if (new_format and len(parts) > 1) else ""

        explicit_code = bool(raw_code and len(raw_code) >= 10 and "-" in raw_code)
        project_val = (project_raw or parsed.get("project") or "T202").strip().upper() or "T202"

        if explicit_code:
            mdr_code = (parsed.get("mdr") or mdr_raw or "E").strip().upper() or "E"
            phase_val = (parsed.get("phase") or phase_raw or "X").strip().upper() or "X"
            disc_val = (parsed.get("disc") or disc_raw or "GN").strip().upper() or "GN"
            pkg_val = (parsed.get("pkg") or pkg_raw or "00").strip().upper() or "00"
            block_val = (parsed.get("block") or block_raw or "G").strip().upper() or "G"
            level_val = (parsed.get("level") or level_raw or "GEN").strip().upper() or "GEN"
        else:
            mdr_code = lookup_cache.resolve_mdr_code(mdr_raw or parsed.get("mdr"), fallback="E")
            phase_val = lookup_cache.resolve_phase_code(phase_raw or parsed.get("phase"), fallback="X")
            disc_val = lookup_cache.resolve_discipline_code(disc_raw or parsed.get("disc"), fallback="GN")
            pkg_val = lookup_cache.resolve_package_code(
                disc_val,
                pkg_raw or parsed.get("pkg"),
                fallback=(parsed.get("pkg") or "00"),
            )
            block_val = (block_raw or parsed.get("block") or "G").strip().upper() or "G"
            level_val = lookup_cache.resolve_level_code(level_raw or parsed.get("level"), fallback="GEN")

        block_val = (block_val[:1] if block_val else "G") or "G"

        generated_code = not raw_code or len(raw_code) < 10 or "-" not in raw_code
        base_prefix = f"{project_val}-{mdr_code}{phase_val}{pkg_val}"
        subject_norm = _normalize_subject(subject_val)
        has_subject_meta_key = bool(subject_norm)
        meta_full_key = (
            project_val,
            mdr_code,
            phase_val,
            disc_val,
            pkg_val,
            block_val,
            level_val,
            subject_norm,
        )

        row_status = {"doc_number": raw_code, "status": "Pending", "msg": ""}

        try:
            lookup_cache.ensure(
                project_val, phase_val, disc_val, pkg_val, level_val, mdr_code
            )

            if has_subject_meta_key:
                existing_doc_by_key = duplicate_meta_cache.find_existing_doc(
                    project_val,
                    mdr_code,
                    phase_val,
                    disc_val,
                    pkg_val,
                    block_val,
                    level_val,
                    subject_val,
                )
                if existing_doc_by_key:
                    row_status["doc_number"] = existing_doc_by_key
                    row_status["status"] = "Skipped"
                    row_status["msg"] = f"Duplicate (metadata key exists: {existing_doc_by_key})"
                    results["details"].append(row_status)
                    continue

                if meta_full_key in batch_meta_keys:
                    row_status["doc_number"] = batch_meta_keys[meta_full_key]
                    row_status["status"] = "Skipped"
                    row_status["msg"] = f"Duplicate (same metadata key in current batch: {batch_meta_keys[meta_full_key]})"
                    results["details"].append(row_status)
                    continue

            if generated_code:
                existing_doc_numbers.update(serial_cache.get_existing_doc_numbers(base_prefix))
                final_serial = serial_cache.resolve_serial(base_prefix, subject_val)
                doc_to_save = f"{project_val}-{mdr_code}{phase_val}{pkg_val}{final_serial}-{block_val}{level_val}"
            else:
                doc_to_save = raw_code
            row_status["doc_number"] = doc_to_save

            if doc_to_save in existing_doc_numbers:
                row_status["status"] = "Skipped"
                row_status["msg"] = "Duplicate (Document exists)"
                results["details"].append(row_status)
                continue

            if doc_to_save in batch_doc_numbers:
                row_status["status"] = "Skipped"
                row_status["msg"] = "Duplicate (In current batch)"
                results["details"].append(row_status)
                continue

            pkg_name_e, pkg_name_p = lookup_cache.get_package_names(disc_val, pkg_val)
            level_name_p = lookup_cache.get_level_name_p(level_val)
            title_e, title_p = _build_full_titles(
                pkg_name_e,
                pkg_name_p,
                pkg_val,
                block_val,
                level_val,
                level_name_p,
                subject_val,
            )

            new_documents.append(
                MdrDocument(
                    doc_number=doc_to_save,
                    project_code=project_val,
                    mdr_code=mdr_code,
                    phase_code=phase_val,
                    discipline_code=disc_val,
                    package_code=pkg_val,
                    block=block_val,
                    level_code=level_val,
                    doc_title_e=title_e,
                    doc_title_p=title_p,
                    subject=subject_val,
                )
            )

            batch_doc_numbers.add(doc_to_save)
            existing_doc_numbers.add(doc_to_save)
            if has_subject_meta_key:
                batch_meta_keys[meta_full_key] = doc_to_save
                duplicate_meta_cache.mark_new_doc(
                    project_val,
                    mdr_code,
                    phase_val,
                    disc_val,
                    pkg_val,
                    block_val,
                    level_val,
                    subject_val,
                    doc_to_save,
                )
            if generated_code:
                serial_cache.mark_doc_number(base_prefix, doc_to_save)

            row_status["status"] = "Success"
            results["success"] += 1
        except Exception as exc:
            print(f"Error processing {doc_to_save}: {exc}")
            row_status["status"] = "Failed"
            row_status["msg"] = str(exc)
            results["failed"] += 1

        results["details"].append(row_status)

    try:
        if new_documents:
            db.add_all(new_documents)
        db.commit()
    except Exception as exc:
        db.rollback()
        return {"ok": False, "message": f"DB Commit Error: {exc}"}

    return {
        "ok": True,
        "stats": results,
        "message": f"{results['success']} Document(s) registered successfully.",
    }
