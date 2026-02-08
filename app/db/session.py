# app/db/session.py
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Generator, List
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.core.organizations import (
    ALL_ORG_ROLES,
    PERMISSION_CATEGORIES,
    OrganizationRole,
    OrganizationType,
    normalize_org_role,
    normalize_permission_category,
)
from app.core.roles import ALL_ROLES, ROLE_PERMISSIONS, Role
from app.db.base import Base

def _normalize_sqlite_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("DATABASE_URL is empty. Set it in .env")

    # اگر کاربر فقط مسیر داده بود، تبدیل به sqlite:///...
    if "://" not in url:
        # مثال: .\database\mdr_project.db
        path = url.replace("\\", "/")
        if not path.startswith("/"):
            return f"sqlite:///{path}"
        return f"sqlite://{path}"

    # اگر sqlite:///relative بود، بک‌اسلش‌ها را اصلاح کنیم
    if url.startswith("sqlite:///"):
        return url.replace("\\", "/")

    return url


DATABASE_URL = _normalize_sqlite_url(settings.DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _normalize_state(value: Any) -> str:
    state = str(value or "").strip().lower()
    if state in {"draft", "issued", "void"}:
        return state
    return "issued"


def _parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _safe_json_dict(raw: str | None) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _permission_keys() -> List[str]:
    keys: set[str] = set()
    for perms in ROLE_PERMISSIONS.values():
        for perm in perms:
            if perm != "*":
                keys.add(perm)
    return sorted(keys)


def _sqlite_column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(str(row[1]) == column_name for row in rows)


def _sqlite_table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name=:table_name"
        ),
        {"table_name": table_name},
    ).fetchone()
    return bool(row)


def _sqlite_index_exists(conn, index_name: str) -> bool:
    row = conn.execute(
        text(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name=:index_name"
        ),
        {"index_name": index_name},
    ).fetchone()
    return bool(row)


def _sqlite_add_column_if_missing(conn, table_name: str, column_name: str, column_sql: str) -> None:
    if not _sqlite_table_exists(conn, table_name):
        return
    if _sqlite_column_exists(conn, table_name, column_name):
        return
    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))


def _sqlite_create_index_if_missing(conn, index_name: str, create_sql: str) -> None:
    if _sqlite_index_exists(conn, index_name):
        return
    try:
        conn.execute(text(create_sql))
    except Exception as exc:
        print(f"[WARN] Failed creating index `{index_name}`: {exc}")


def _ensure_sqlite_schema_updates() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        if not _sqlite_table_exists(conn, "issuing_entities"):
            conn.execute(
                text(
                    """
                    CREATE TABLE issuing_entities (
                        code VARCHAR(20) PRIMARY KEY,
                        name_e VARCHAR(255) NOT NULL,
                        name_p VARCHAR(255),
                        project_code VARCHAR(50),
                        is_active BOOLEAN DEFAULT 1,
                        sort_order INTEGER DEFAULT 0
                    )
                    """
                )
            )
        if not _sqlite_table_exists(conn, "correspondence_categories"):
            conn.execute(
                text(
                    """
                    CREATE TABLE correspondence_categories (
                        code VARCHAR(20) PRIMARY KEY,
                        name_e VARCHAR(255) NOT NULL,
                        name_p VARCHAR(255),
                        is_active BOOLEAN DEFAULT 1,
                        sort_order INTEGER DEFAULT 0
                    )
                    """
                )
            )
        _sqlite_add_column_if_missing(conn, "transmittals", "lifecycle_status", "VARCHAR(16)")
        _sqlite_add_column_if_missing(conn, "transmittals", "void_reason", "VARCHAR(500)")
        _sqlite_add_column_if_missing(conn, "transmittals", "voided_by", "VARCHAR(255)")
        _sqlite_add_column_if_missing(conn, "transmittals", "voided_at", "DATETIME")
        _sqlite_add_column_if_missing(conn, "archive_files", "file_kind", "VARCHAR(20) DEFAULT 'pdf'")
        _sqlite_add_column_if_missing(conn, "archive_files", "is_primary", "BOOLEAN DEFAULT 1")
        _sqlite_add_column_if_missing(conn, "archive_files", "companion_file_id", "INTEGER")
        _sqlite_add_column_if_missing(conn, "users", "organization_id", "INTEGER")
        _sqlite_add_column_if_missing(conn, "users", "organization_role", "VARCHAR(32) DEFAULT 'viewer'")
        _sqlite_add_column_if_missing(conn, "workboard_items", "organization_id", "INTEGER")
        _sqlite_add_column_if_missing(
            conn,
            "correspondence_attachments",
            "file_kind",
            "VARCHAR(20) DEFAULT 'attachment'",
        )
        _sqlite_add_column_if_missing(conn, "correspondences", "issuing_code", "VARCHAR(20)")
        _sqlite_add_column_if_missing(conn, "correspondences", "category_code", "VARCHAR(20)")
        _sqlite_create_index_if_missing(
            conn,
            "ix_correspondences_issuing_code",
            "CREATE INDEX ix_correspondences_issuing_code ON correspondences(issuing_code)",
        )
        _sqlite_create_index_if_missing(
            conn,
            "ix_correspondences_category_code",
            "CREATE INDEX ix_correspondences_category_code ON correspondences(category_code)",
        )
        _sqlite_create_index_if_missing(
            conn,
            "uq_correspondences_reference_no",
            "CREATE UNIQUE INDEX uq_correspondences_reference_no "
            "ON correspondences(reference_no) WHERE reference_no IS NOT NULL",
        )
        _sqlite_create_index_if_missing(
            conn,
            "ix_users_organization_id",
            "CREATE INDEX ix_users_organization_id ON users(organization_id)",
        )
        _sqlite_create_index_if_missing(
            conn,
            "ix_organizations_parent",
            "CREATE INDEX ix_organizations_parent ON organizations(parent_id)",
        )
        _sqlite_create_index_if_missing(
            conn,
            "ix_organizations_type",
            "CREATE INDEX ix_organizations_type ON organizations(org_type)",
        )
        _sqlite_create_index_if_missing(
            conn,
            "ix_workboard_items_organization_id",
            "CREATE INDEX ix_workboard_items_organization_id ON workboard_items(organization_id)",
        )
        _sqlite_create_index_if_missing(
            conn,
            "ix_workboard_org_module_tab",
            "CREATE INDEX ix_workboard_org_module_tab ON workboard_items(organization_id, module_key, tab_key)",
        )


def _migrate_transmittal_state_from_kv(db: Session) -> None:
    from app.db.models import SettingsKV, Transmittal

    row = db.query(SettingsKV).filter(SettingsKV.key == "transmittal.state.v1").first()
    payload = _safe_json_dict(row.value if row else None)
    if not payload:
        return

    for transmittal_id, state_payload in payload.items():
        transmittal = db.query(Transmittal).filter(Transmittal.id == str(transmittal_id)).first()
        if not transmittal:
            continue

        if isinstance(state_payload, dict):
            status = _normalize_state(state_payload.get("status"))
            void_reason = str(state_payload.get("void_reason") or "").strip() or None
            voided_by = str(state_payload.get("voided_by") or "").strip() or None
            voided_at = _parse_dt(state_payload.get("voided_at"))
        else:
            status = _normalize_state(state_payload)
            void_reason = None
            voided_by = None
            voided_at = None

        if not transmittal.lifecycle_status:
            transmittal.lifecycle_status = status
        if status == "void":
            if void_reason and not transmittal.void_reason:
                transmittal.void_reason = void_reason
            if voided_by and not transmittal.voided_by:
                transmittal.voided_by = voided_by
            if voided_at and not transmittal.voided_at:
                transmittal.voided_at = voided_at


def _backfill_transmittal_state_defaults(db: Session) -> None:
    from app.db.models import Transmittal

    rows = db.query(Transmittal).all()
    for row in rows:
        if not row.lifecycle_status:
            row.lifecycle_status = "issued" if row.send_date else "draft"
        row.lifecycle_status = _normalize_state(row.lifecycle_status)
        if row.lifecycle_status != "void":
            row.void_reason = None
            row.voided_by = None
            row.voided_at = None


def _normalize_archive_file_kind(value: Any) -> str:
    kind = str(value or "").strip().lower()
    if kind in {"pdf", "native"}:
        return kind
    return "pdf"


def _backfill_archive_file_defaults(db: Session) -> None:
    from app.db.models import ArchiveFile

    if DATABASE_URL.startswith("sqlite"):
        row = db.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name=:table_name"
            ),
            {"table_name": "archive_files"},
        ).fetchone()
        if not row:
            return

    rows = db.query(ArchiveFile).all()
    for row in rows:
        row.file_kind = _normalize_archive_file_kind(getattr(row, "file_kind", None))
        if row.is_primary is None:
            row.is_primary = True


def _normalize_corr_attachment_kind(value: Any) -> str:
    kind = str(value or "").strip().lower()
    if kind in {"letter", "original", "attachment"}:
        return kind
    return "attachment"


def _backfill_correspondence_attachment_defaults(db: Session) -> None:
    from app.db.models import CorrespondenceAttachment

    if DATABASE_URL.startswith("sqlite"):
        row = db.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name=:table_name"
            ),
            {"table_name": "correspondence_attachments"},
        ).fetchone()
        if not row:
            return

    rows = db.query(CorrespondenceAttachment).all()
    for row in rows:
        row.file_kind = _normalize_corr_attachment_kind(getattr(row, "file_kind", None))


def _corr_category_code_from_doc_type(value: Any) -> str:
    raw = str(value or "").strip().upper()
    mapping = {
        "LETTER": "CO",
        "CORRESPONDENCE": "CO",
        "MOM": "M",
        "MEETING": "M",
        "EMAIL": "I",
        "MAIL": "I",
        "LEGAL": "L",
        "PERSONNEL": "S",
        "FINANCE": "F",
        "CONFIDENTIAL": "C",
        "INVOICE": "V",
        "PROFORMA": "P",
    }
    if raw in mapping:
        return mapping[raw]
    alnum = "".join(ch for ch in raw if ch.isalnum())
    return (alnum[:2] if alnum else "CO").upper()


def _seed_correspondence_catalog_defaults(db: Session) -> None:
    from app.db.models import CorrespondenceCategory, IssuingEntity, Project

    issuing_defaults: list[tuple[str, str, str | None, int]] = [
        ("G", "General", None, 10),
        ("EXT", "External", None, 20),
        ("P", "Personnel", None, 30),
        ("B", "Buyers", None, 40),
        ("COM", "ARCA", None, 50),
        ("FIN", "ARCA Finance", None, 60),
    ]
    category_defaults: list[tuple[str, str, int]] = [
        ("CO", "Correspondence", 10),
        ("M", "Meeting Minutes", 20),
        ("I", "Internal Communication", 30),
        ("S", "Personnel", 40),
        ("F", "Finance", 50),
        ("L", "Legal", 60),
        ("C", "Confidential", 70),
        ("V", "Invoice", 80),
        ("P", "Proforma", 90),
    ]

    existing_issuing = {
        str(row.code).strip().upper()
        for row in db.query(IssuingEntity.code).all()
        if str(row.code or "").strip()
    }
    existing_categories = {
        str(row.code).strip().upper()
        for row in db.query(CorrespondenceCategory.code).all()
        if str(row.code or "").strip()
    }

    projects = db.query(Project).all()
    for project in projects:
        code = str(project.code or "").strip().upper()
        if not code or code in existing_issuing:
            continue
        db.add(
            IssuingEntity(
                code=code,
                name_e=str(project.name_e or project.name_p or project.code),
                project_code=code,
                is_active=bool(getattr(project, "is_active", True)),
                sort_order=100,
            )
        )
        existing_issuing.add(code)

    for code, name_e, project_code, sort_order in issuing_defaults:
        if code in existing_issuing:
            continue
        db.add(
            IssuingEntity(
                code=code,
                name_e=name_e,
                project_code=project_code,
                is_active=True,
                sort_order=sort_order,
            )
        )
        existing_issuing.add(code)

    for code, name_e, sort_order in category_defaults:
        if code in existing_categories:
            continue
        db.add(
            CorrespondenceCategory(
                code=code,
                name_e=name_e,
                is_active=True,
                sort_order=sort_order,
            )
        )
        existing_categories.add(code)


def _backfill_correspondence_issuing_category(db: Session) -> None:
    from app.db.models import Correspondence, CorrespondenceCategory, IssuingEntity, Project

    existing_issuing = {
        str(row.code).strip().upper()
        for row in db.query(IssuingEntity.code).all()
        if str(row.code or "").strip()
    }
    existing_categories = {
        str(row.code).strip().upper()
        for row in db.query(CorrespondenceCategory.code).all()
        if str(row.code or "").strip()
    }

    projects = {
        str(row.code).strip().upper(): row
        for row in db.query(Project).all()
        if str(row.code or "").strip()
    }
    fallback_issuing = "COM" if "COM" in existing_issuing else ("G" if "G" in existing_issuing else None)

    rows = db.query(Correspondence).all()
    for row in rows:
        category_code = str(getattr(row, "category_code", "") or "").strip().upper()
        if not category_code:
            category_code = _corr_category_code_from_doc_type(getattr(row, "doc_type", None))
            row.category_code = category_code
        if category_code not in existing_categories and category_code:
            db.add(
                CorrespondenceCategory(
                    code=category_code,
                    name_e=category_code,
                    is_active=True,
                    sort_order=999,
                )
            )
            existing_categories.add(category_code)

        issuing_code = str(getattr(row, "issuing_code", "") or "").strip().upper()
        if not issuing_code:
            project_code = str(getattr(row, "project_code", "") or "").strip().upper()
            issuing_code = project_code or (fallback_issuing or "G")
            row.issuing_code = issuing_code
        if issuing_code not in existing_issuing and issuing_code:
            project = projects.get(issuing_code)
            db.add(
                IssuingEntity(
                    code=issuing_code,
                    name_e=str(
                        (project.name_e if project else None)
                        or (project.name_p if project else None)
                        or issuing_code
                    ),
                    project_code=(issuing_code if project else None),
                    is_active=True,
                    sort_order=999,
                )
            )
            existing_issuing.add(issuing_code)


def _seed_permission_matrix_from_kv(db: Session) -> None:
    from app.db.models import RolePermission, SettingsKV

    if db.query(RolePermission).count() > 0:
        return

    matrix: Dict[str, Dict[str, bool]] = {}
    perms = _permission_keys()
    for role in ALL_ROLES:
        role_enum = Role(role)
        role_perms = ROLE_PERMISSIONS.get(role_enum, [])
        if "*" in role_perms:
            matrix[role] = {p: True for p in perms}
        else:
            matrix[role] = {p: (p in role_perms) for p in perms}

    row = db.query(SettingsKV).filter(SettingsKV.key == "rbac.matrix.v1").first()
    raw = _safe_json_dict(row.value if row else None)
    if raw:
        for role in ALL_ROLES:
            if role == Role.ADMIN.value:
                matrix[role] = {p: True for p in perms}
                continue
            role_raw = raw.get(role)
            if not isinstance(role_raw, dict):
                continue
            for perm in perms:
                if perm in role_raw:
                    matrix[role][perm] = bool(role_raw.get(perm))

    for role in ALL_ROLES:
        for perm in perms:
            db.add(
                RolePermission(
                    role=role,
                    permission=perm,
                    allowed=True if role == Role.ADMIN.value else bool(matrix[role][perm]),
                )
            )


def _backfill_permission_matrix(db: Session) -> None:
    from app.db.models import RolePermission

    perms = _permission_keys()
    existing = {(row.role, row.permission) for row in db.query(RolePermission.role, RolePermission.permission).all()}

    for role in ALL_ROLES:
        role_enum = Role(role)
        role_perms = ROLE_PERMISSIONS.get(role_enum, [])
        has_wildcard = "*" in role_perms
        for perm in perms:
            if (role, perm) in existing:
                continue
            allowed = True if role == Role.ADMIN.value else (has_wildcard or perm in role_perms)
            db.add(RolePermission(role=role, permission=perm, allowed=allowed))

    # Backward-compatibility for environments where DCC was introduced with all-false rows.
    dcc_rows = db.query(RolePermission).filter(RolePermission.role == Role.DCC.value).all()
    if dcc_rows and not any(bool(row.allowed) for row in dcc_rows):
        dcc_defaults = set(ROLE_PERMISSIONS.get(Role.DCC, []))
        has_wildcard = "*" in dcc_defaults
        for row in dcc_rows:
            row.allowed = has_wildcard or (row.permission in dcc_defaults)


def _seed_role_scopes_from_kv(db: Session) -> None:
    from app.db.models import (
        Discipline,
        Project,
        RoleDisciplineScope,
        RoleProjectScope,
        SettingsKV,
    )

    if db.query(RoleProjectScope).count() > 0 or db.query(RoleDisciplineScope).count() > 0:
        return

    existing_projects = {code for (code,) in db.query(Project.code).all()}
    existing_disciplines = {code for (code,) in db.query(Discipline.code).all()}

    row = db.query(SettingsKV).filter(SettingsKV.key == "rbac.scope.v1").first()
    raw = _safe_json_dict(row.value if row else None)
    if not raw:
        return

    for role in ALL_ROLES:
        role_data = raw.get(role)
        if not isinstance(role_data, dict):
            continue

        projects = sorted({str(v or "").strip().upper() for v in role_data.get("projects", []) if str(v or "").strip()})
        disciplines = sorted({str(v or "").strip().upper() for v in role_data.get("disciplines", []) if str(v or "").strip()})

        for code in projects:
            if code in existing_projects:
                db.add(RoleProjectScope(role=role, project_code=code))
        for code in disciplines:
            if code in existing_disciplines:
                db.add(RoleDisciplineScope(role=role, discipline_code=code))


def _seed_user_scopes_from_kv(db: Session) -> None:
    from app.db.models import (
        Discipline,
        Project,
        SettingsKV,
        User,
        UserDisciplineScope,
        UserProjectScope,
    )

    if db.query(UserProjectScope).count() > 0 or db.query(UserDisciplineScope).count() > 0:
        return

    existing_users = {uid for (uid,) in db.query(User.id).all()}
    existing_projects = {code for (code,) in db.query(Project.code).all()}
    existing_disciplines = {code for (code,) in db.query(Discipline.code).all()}

    row = db.query(SettingsKV).filter(SettingsKV.key == "rbac.user_scope.v1").first()
    raw = _safe_json_dict(row.value if row else None)
    if not raw:
        return

    for user_id, user_data in raw.items():
        try:
            uid = int(user_id)
        except Exception:
            continue
        if uid not in existing_users or not isinstance(user_data, dict):
            continue

        projects = sorted({str(v or "").strip().upper() for v in user_data.get("projects", []) if str(v or "").strip()})
        disciplines = sorted({str(v or "").strip().upper() for v in user_data.get("disciplines", []) if str(v or "").strip()})
        for code in projects:
            if code in existing_projects:
                db.add(UserProjectScope(user_id=uid, project_code=code))
        for code in disciplines:
            if code in existing_disciplines:
                db.add(UserDisciplineScope(user_id=uid, discipline_code=code))


def _seed_organization_defaults(db: Session) -> None:
    from app.db.models import Organization

    existing = {
        str(row.code or "").strip().upper(): row
        for row in db.query(Organization).all()
        if str(row.code or "").strip()
    }

    seed_rows: list[tuple[str, str, str]] = [
        ("SYSTEM_ROOT", "System Root", OrganizationType.SYSTEM.value),
        ("EMPLOYER_ROOT", "Employer", OrganizationType.EMPLOYER.value),
        ("CONSULTANT_ROOT", "Consultant", OrganizationType.CONSULTANT.value),
        ("CONTRACTOR_ROOT", "Contractor", OrganizationType.CONTRACTOR.value),
    ]

    for code, name, org_type in seed_rows:
        if code in existing:
            continue
        row = Organization(
            code=code,
            name=name,
            org_type=org_type,
            is_active=True,
        )
        db.add(row)
        existing[code] = row

    db.flush()

    system_root = existing.get("SYSTEM_ROOT")
    if system_root:
        for code in ("EMPLOYER_ROOT", "CONSULTANT_ROOT", "CONTRACTOR_ROOT"):
            row = existing.get(code)
            if row and row.parent_id is None:
                row.parent_id = system_root.id


def _normalize_seed_org_role(system_role: str) -> str:
    role_key = str(system_role or "").strip().lower()
    if role_key == Role.ADMIN.value:
        return OrganizationRole.ADMIN.value
    if role_key == Role.DCC.value:
        return OrganizationRole.DCC.value
    return OrganizationRole.VIEWER.value


def _backfill_user_organization_defaults(db: Session) -> None:
    from app.db.models import Organization, User

    system_root = (
        db.query(Organization)
        .filter(Organization.code == "SYSTEM_ROOT")
        .first()
    )
    if not system_root:
        return

    users = db.query(User).all()
    for user in users:
        if getattr(user, "organization_id", None) is None:
            user.organization_id = system_root.id

        role_value = normalize_org_role(getattr(user, "organization_role", None))
        if role_value not in ALL_ORG_ROLES:
            user.organization_role = _normalize_seed_org_role(getattr(user, "role", None))


def _seed_role_category_rules_from_base(db: Session) -> None:
    from app.db.models import (
        RoleCategoryDisciplineScope,
        RoleCategoryPermission,
        RoleCategoryProjectScope,
        RoleDisciplineScope,
        RolePermission,
        RoleProjectScope,
    )

    has_seed = (
        db.query(RoleCategoryPermission.id).first()
        or db.query(RoleCategoryProjectScope.id).first()
        or db.query(RoleCategoryDisciplineScope.id).first()
    )
    if has_seed:
        return

    role_perm_rows = db.query(RolePermission.role, RolePermission.permission, RolePermission.allowed).all()
    role_project_rows = db.query(RoleProjectScope.role, RoleProjectScope.project_code).all()
    role_discipline_rows = db.query(RoleDisciplineScope.role, RoleDisciplineScope.discipline_code).all()

    if not role_perm_rows:
        perms = _permission_keys()
        for role in ALL_ROLES:
            role_enum = Role(role)
            role_perms = ROLE_PERMISSIONS.get(role_enum, [])
            has_wildcard = "*" in role_perms
            for perm in perms:
                role_perm_rows.append(
                    (
                        role,
                        perm,
                        True if role == Role.ADMIN.value else (has_wildcard or perm in role_perms),
                    )
                )

    for category in PERMISSION_CATEGORIES:
        category_key = normalize_permission_category(category)
        for role, permission, allowed in role_perm_rows:
            db.add(
                RoleCategoryPermission(
                    category=category_key,
                    role=str(role or "").strip().lower(),
                    permission=str(permission or "").strip(),
                    allowed=bool(allowed),
                )
            )
        for role, project_code in role_project_rows:
            if not str(project_code or "").strip():
                continue
            db.add(
                RoleCategoryProjectScope(
                    category=category_key,
                    role=str(role or "").strip().lower(),
                    project_code=str(project_code or "").strip().upper(),
                )
            )
        for role, discipline_code in role_discipline_rows:
            if not str(discipline_code or "").strip():
                continue
            db.add(
                RoleCategoryDisciplineScope(
                    category=category_key,
                    role=str(role or "").strip().lower(),
                    discipline_code=str(discipline_code or "").strip().upper(),
                )
            )


def _backfill_workboard_organization_defaults(db: Session) -> None:
    from app.db.models import Organization, User, WorkboardItem

    users_org_map = {
        int(uid): int(org_id)
        for uid, org_id in db.query(User.id, User.organization_id).all()
        if uid is not None and org_id is not None
    }
    org_by_code = {
        str(code or "").strip().upper(): int(org_id)
        for org_id, code in db.query(Organization.id, Organization.code).all()
    }
    system_root_id = org_by_code.get("SYSTEM_ROOT")
    consultant_root_id = org_by_code.get("CONSULTANT_ROOT")
    contractor_root_id = org_by_code.get("CONTRACTOR_ROOT")

    rows = db.query(WorkboardItem).filter(WorkboardItem.organization_id.is_(None)).all()
    for row in rows:
        assigned = users_org_map.get(int(row.created_by_id or 0))
        if assigned is None:
            module_key = str(getattr(row, "module_key", "") or "").strip().lower()
            if module_key == "contractor":
                assigned = contractor_root_id or system_root_id
            elif module_key == "consultant":
                assigned = consultant_root_id or system_root_id
            else:
                assigned = system_root_id
        row.organization_id = assigned


def _archive_and_drop_legacy_kv(db: Session) -> None:
    from app.db.models import RolePermission, SettingsKV

    legacy_sources = [
        ("transmittal.state.v1", "legacy.tr.state.v1"),
        ("rbac.matrix.v1", "legacy.rbac.matrix.v1"),
        ("rbac.scope.v1", "legacy.rbac.scope.v1"),
        ("rbac.user_scope.v1", "legacy.rbac.user_scope.v1"),
    ]

    # Gate cleanup by relational readiness.
    if db.query(RolePermission).count() <= 0:
        return

    for source_key, backup_key in legacy_sources:
        row = db.query(SettingsKV).filter(SettingsKV.key == source_key).first()
        if not row:
            continue

        backup = db.query(SettingsKV).filter(SettingsKV.key == backup_key).first()
        if not backup:
            db.add(
                SettingsKV(
                    key=backup_key,
                    value=row.value,
                    updated_at=datetime.utcnow(),
                )
            )
        db.delete(row)


def _run_smart_migrations() -> None:
    with SessionLocal() as db:
        _migrate_transmittal_state_from_kv(db)
        _backfill_transmittal_state_defaults(db)
        _backfill_archive_file_defaults(db)
        _backfill_correspondence_attachment_defaults(db)
        _seed_correspondence_catalog_defaults(db)
        # flush seeded catalog rows before correspondence backfill.
        db.flush()
        _backfill_correspondence_issuing_category(db)
        _seed_permission_matrix_from_kv(db)
        # SessionLocal has autoflush=False; flush seeded rows before backfill checks.
        db.flush()
        _backfill_permission_matrix(db)
        _seed_role_scopes_from_kv(db)
        _seed_user_scopes_from_kv(db)
        _seed_organization_defaults(db)
        db.flush()
        _backfill_user_organization_defaults(db)
        _backfill_workboard_organization_defaults(db)
        _seed_role_category_rules_from_base(db)
        _archive_and_drop_legacy_kv(db)
        db.commit()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    جداول دیتابیس را می‌سازد.
    """
    # ✅ نکته حیاتی: ایمپورت مدل‌ها قبل از create_all
    # این باعث می‌شود SQLAlchemy تمام جداول تعریف شده در models.py را بشناسد
    import app.db.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_schema_updates()

    # ✅ ساخت دستی جدول DocStatus اگر وجود نداشته باشد
    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            # چک می‌کنیم جدول وجود دارد یا نه
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='doc_statuses'"
            )).fetchone()
            
            if not result:
                print("[INFO] Creating doc_statuses table manually...")
                conn.execute(text("""
                    CREATE TABLE doc_statuses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code VARCHAR(20) UNIQUE NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        description VARCHAR(255),
                        sort_order INTEGER DEFAULT 0
                    )
                """))
                print("[INFO] doc_statuses table created successfully.")

    # فعال‌سازی FK در SQLite (چون به صورت پیش‌فرض خاموش است)
    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys=ON;"))

    _run_smart_migrations()


def list_tables() -> List[str]:
    """
    لیست جدول‌ها از sqlite_master (بدون جدول‌های داخلی sqlite_)
    """
    if not DATABASE_URL.startswith("sqlite"):
        return []

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ).fetchall()
    return [r[0] for r in rows]
