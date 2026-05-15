from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.orm import joinedload

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.dependencies import _load_allowed_permissions
from app.core.access_matrix import (
    CANONICAL_MATRIX_ROLES,
    CANONICAL_PERMISSION_CATEGORIES,
    build_navigation_state,
    canonical_permission_count,
)
from app.core.permission_catalog import permission_keys
from app.db.models import RoleCategoryPermission, User
from app.db.session import SessionLocal
from app.services.access_control import resolve_effective_access


def _print_json(title: str, payload: Any) -> None:
    print(f"\n{title}")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def check_matrix() -> int:
    expected = canonical_permission_count()
    with SessionLocal() as db:
        rows = db.query(
            RoleCategoryPermission.category,
            RoleCategoryPermission.role,
            RoleCategoryPermission.permission,
        ).all()
    counts: dict[tuple[str, str], int] = {}
    for category, role, permission in rows:
        key = (str(category or "").strip().lower(), str(role or "").strip().lower())
        if str(permission or "").strip():
            counts[key] = counts.get(key, 0) + 1

    print(f"canonical_permission_count = {expected}")
    ok = True
    for category in CANONICAL_PERMISSION_CATEGORIES:
        for role in CANONICAL_MATRIX_ROLES:
            actual = counts.get((category, role), 0)
            status = "OK" if actual == expected else "MISMATCH"
            print(f"{category:<12} {role:<8} actual={actual:<4} expected={expected:<4} {status}")
            if actual != expected:
                ok = False
    return 0 if ok else 1


def diagnose_user(user_id: int) -> int:
    with SessionLocal() as db:
        user = (
            db.query(User)
            .options(joinedload(User.organization))
            .filter(User.id == int(user_id))
            .first()
        )
        if not user:
            print(f"user {user_id} not found")
            return 1

        access = resolve_effective_access(user)
        allowed = _load_allowed_permissions(
            db,
            access.effective_role,
            category=access.permission_category,
        )
        capabilities = {permission: ("*" in allowed or permission in allowed) for permission in permission_keys()}
        navigation = build_navigation_state(
            capabilities,
            category=access.permission_category,
            effective_role=access.effective_role,
        )

        summary = {
            "user_id": user.id,
            "email": user.email,
            "organization_type": access.organization_type,
            "organization_role": getattr(user, "organization_role", None),
            "effective_role": access.effective_role,
            "permission_category": access.permission_category,
            "is_system_admin": access.is_system_admin,
            "full_access": access.full_access,
        }
        _print_json("user", summary)
        _print_json("navigation", navigation)
        denied = sorted(permission for permission, is_allowed in capabilities.items() if not is_allowed)[:25]
        _print_json("sample_denied_permissions", denied)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose access-control matrix and effective navigation.")
    parser.add_argument("--check-matrix", action="store_true", help="Check row coverage for every (category, role).")
    parser.add_argument("--user-id", type=int, help="Inspect effective access for a specific user.")
    args = parser.parse_args()

    exit_code = 0
    if args.check_matrix:
        exit_code = max(exit_code, check_matrix())
    if args.user_id:
        exit_code = max(exit_code, diagnose_user(args.user_id))
    if not args.check_matrix and not args.user_id:
        parser.print_help()
        return 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
