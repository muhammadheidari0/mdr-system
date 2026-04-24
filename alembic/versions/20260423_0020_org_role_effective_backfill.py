"""Backfill organization_role-driven effective access.

Revision ID: 20260423_0020
Revises: 20260422_0019
Create Date: 2026-04-23 08:30:00
"""
from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "20260423_0020"
down_revision = "20260422_0019"
branch_labels = None
depends_on = None


ROLE_ADMIN = "admin"
MATRIX_ROLES = {"manager", "dcc", "user", "viewer"}
SYSTEM_ORG_TYPE = "system"
SYSTEM_ROOT_CODE = "SYSTEM_ROOT"


def _norm(value: object) -> str:
    return str(value or "").strip().lower()


def _resolve_effective_for_non_system(*, legacy_role: str, organization_role: str) -> tuple[str, str]:
    org_role = _norm(organization_role)
    role = _norm(legacy_role)

    if org_role == ROLE_ADMIN:
        org_role = "manager"
    if org_role not in MATRIX_ROLES:
        org_role = role if role in MATRIX_ROLES else "viewer"

    return org_role, org_role


def _ensure_system_root(bind, organizations) -> int:
    by_code = bind.execute(
        sa.select(organizations.c.id).where(organizations.c.code == SYSTEM_ROOT_CODE).limit(1)
    ).first()
    if by_code:
        return int(by_code[0])

    existing_system = bind.execute(
        sa.select(organizations.c.id)
        .where(organizations.c.org_type == SYSTEM_ORG_TYPE)
        .order_by(organizations.c.id.asc())
        .limit(1)
    ).first()
    if existing_system:
        return int(existing_system[0])

    now = datetime.utcnow()
    bind.execute(
        sa.insert(organizations).values(
            code=SYSTEM_ROOT_CODE,
            name="System Root",
            org_type=SYSTEM_ORG_TYPE,
            parent_id=None,
            is_active=True,
            created_at=now,
        )
    )
    inserted = bind.execute(
        sa.select(organizations.c.id).where(organizations.c.code == SYSTEM_ROOT_CODE).limit(1)
    ).first()
    if not inserted:
        raise RuntimeError("Failed to create SYSTEM_ROOT organization.")
    return int(inserted[0])


def upgrade() -> None:
    bind = op.get_bind()

    organizations = sa.table(
        "organizations",
        sa.column("id", sa.Integer),
        sa.column("code", sa.String),
        sa.column("org_type", sa.String),
        sa.column("name", sa.String),
        sa.column("parent_id", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("role", sa.String),
        sa.column("organization_id", sa.Integer),
        sa.column("organization_role", sa.String),
    )

    system_root_id = _ensure_system_root(bind, organizations)

    org_rows = bind.execute(
        sa.select(organizations.c.id, organizations.c.org_type)
    ).all()
    org_type_by_id = {int(row[0]): _norm(row[1]) for row in org_rows if row and row[0] is not None}

    user_rows = bind.execute(
        sa.select(
            users.c.id,
            users.c.role,
            users.c.organization_id,
            users.c.organization_role,
        )
    ).all()

    for row in user_rows:
        user_id = int(row[0])
        legacy_role = _norm(row[1])
        organization_id = int(row[2]) if row[2] is not None else None
        organization_role = _norm(row[3])
        organization_type = org_type_by_id.get(int(organization_id or 0), "")

        is_system_user = organization_type == SYSTEM_ORG_TYPE
        if legacy_role == ROLE_ADMIN and not is_system_user:
            organization_id = system_root_id
            is_system_user = True

        if is_system_user:
            target_role = ROLE_ADMIN
            target_org_role = ROLE_ADMIN
            target_org_id = organization_id or system_root_id
        else:
            target_org_role, target_role = _resolve_effective_for_non_system(
                legacy_role=legacy_role,
                organization_role=organization_role,
            )
            target_org_id = organization_id

        bind.execute(
            sa.update(users)
            .where(users.c.id == user_id)
            .values(
                role=target_role,
                organization_role=target_org_role,
                organization_id=target_org_id,
            )
        )


def downgrade() -> None:
    # Data migration is intentionally non-reversible.
    pass
