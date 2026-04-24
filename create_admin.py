#!/usr/bin/env python3
"""
Create or reset admin user password.

Environment variables:
- ADMIN_EMAIL (default: admin@mdr.local)
- ADMIN_PASSWORD (optional; if missing a strong random password is generated)
- ADMIN_FULL_NAME (default: System Administrator)
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from sqlalchemy.orm import Session

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.core.security import MAX_BCRYPT_PASSWORD_BYTES, get_password_hash  # noqa: E402
from app.db.models import Organization, User  # noqa: E402
from app.db.session import engine  # noqa: E402


def _read_admin_config() -> tuple[str, str, str, bool]:
    email = os.getenv("ADMIN_EMAIL", "admin@mdr.local").strip().lower()
    full_name = os.getenv("ADMIN_FULL_NAME", "System Administrator").strip()

    raw_password = os.getenv("ADMIN_PASSWORD", "").strip()
    generated_password = False
    if not raw_password:
        raw_password = secrets.token_urlsafe(18)
        generated_password = True

    password_bytes = len(raw_password.encode("utf-8"))
    if password_bytes > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(
            f"ADMIN_PASSWORD exceeds bcrypt {MAX_BCRYPT_PASSWORD_BYTES}-byte limit."
        )

    return email, full_name, raw_password, generated_password


def create_or_update_admin() -> None:
    email, full_name, password, generated_password = _read_admin_config()

    print(f"Starting admin sync for: {email}")
    with Session(engine) as db:
        system_root = db.query(Organization).filter(Organization.code == "SYSTEM_ROOT").first()
        if not system_root:
            system_root = db.query(Organization).filter(Organization.org_type == "system").first()
        if not system_root:
            system_root = Organization(
                code="SYSTEM_ROOT",
                name="System Root",
                org_type="system",
                is_active=True,
            )
            db.add(system_root)
            db.flush()

        user = db.query(User).filter(User.email == email).first()
        hashed = get_password_hash(password)

        if user:
            user.hashed_password = hashed
            user.full_name = full_name or user.full_name
            user.is_active = True
            user.role = "admin"
            user.organization_id = system_root.id
            user.organization_role = "admin"
            action = "updated"
        else:
            user = User(
                email=email,
                hashed_password=hashed,
                full_name=full_name,
                role="admin",
                organization_id=system_root.id,
                organization_role="admin",
                is_active=True,
            )
            db.add(user)
            action = "created"

        db.commit()

    print(f"Admin user {email} {action} successfully.")
    if generated_password:
        print(f"Generated ADMIN_PASSWORD: {password}")
        print("Set this in your .env (and TEST_ADMIN_PASSWORD if used in tests).")
    else:
        print("Password was read from ADMIN_PASSWORD env var.")


if __name__ == "__main__":
    try:
        create_or_update_admin()
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
