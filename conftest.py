from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.models import (
    CorrespondenceCategory,
    Discipline,
    IssuingEntity,
    Level,
    MdrCategory,
    Package,
    Phase,
    Project,
    User,
)
from app.db.session import engine, init_db


SEED_PROJECT_CODE = "TSEED"
LEGACY_PROJECT_CODE = "T202"
SEED_MANAGER_EMAIL = "seed.manager@mdr.local"


def _ensure_user(db: Session, *, email: str, password: str, full_name: str, role: str) -> None:
    user = db.query(User).filter(User.email == email).first()
    hashed = get_password_hash(password)
    if user:
        user.hashed_password = hashed
        user.full_name = full_name
        user.role = role
        user.is_active = True
        return

    db.add(
        User(
            email=email,
            hashed_password=hashed,
            full_name=full_name,
            role=role,
            is_active=True,
        )
    )


@pytest.fixture(scope="session", autouse=True)
def deterministic_seed_data() -> None:
    """
    Seed a deterministic minimum dataset so regression tests never depend on
    pre-existing random state from local/dev databases.
    """
    init_db()

    admin_email = str(settings.TEST_ADMIN_EMAIL or "admin@mdr.local").strip().lower()
    admin_password = str(settings.TEST_ADMIN_PASSWORD or "ChangeMe#12345").strip() or "ChangeMe#12345"

    with Session(engine) as db:
        _ensure_user(
            db,
            email=admin_email,
            password=admin_password,
            full_name="System Administrator",
            role="admin",
        )
        _ensure_user(
            db,
            email=SEED_MANAGER_EMAIL,
            password="SeedManager#12345",
            full_name="Seed Manager",
            role="manager",
        )

        if not db.query(Project).filter(Project.code == SEED_PROJECT_CODE).first():
            db.add(
                Project(
                    code=SEED_PROJECT_CODE,
                    name_e="Seed Project",
                    name_p="Seed Project",
                    is_active=True,
                )
            )
        if not db.query(Project).filter(Project.code == LEGACY_PROJECT_CODE).first():
            db.add(
                Project(
                    code=LEGACY_PROJECT_CODE,
                    name_e="Legacy Test Project",
                    name_p="Legacy Test Project",
                    is_active=True,
                )
            )

        if not db.query(Phase).filter(Phase.ph_code == "X").first():
            db.add(Phase(ph_code="X", name_e="Phase X", name_p="Phase X"))

        if not db.query(Discipline).filter(Discipline.code == "GN").first():
            db.add(Discipline(code="GN", name_e="General", name_p="General"))

        if not db.query(Level).filter(Level.code == "GEN").first():
            db.add(Level(code="GEN", name_e="General", name_p="General", sort_order=10))

        if not db.query(MdrCategory).filter(MdrCategory.code == "E").first():
            db.add(
                MdrCategory(
                    code="E",
                    name_e="Engineering",
                    name_p="Engineering",
                    is_active=True,
                    sort_order=10,
                )
            )

        if not db.query(Package).filter(Package.discipline_code == "GN", Package.package_code == "00").first():
            db.add(
                Package(
                    discipline_code="GN",
                    package_code="00",
                    name_e="Package 00",
                    name_p="Package 00",
                )
            )

        if not db.query(IssuingEntity).filter(IssuingEntity.code == "G").first():
            db.add(
                IssuingEntity(
                    code="G",
                    name_e="General",
                    name_p="General",
                    project_code=None,
                    is_active=True,
                    sort_order=10,
                )
            )

        if not db.query(IssuingEntity).filter(IssuingEntity.code == SEED_PROJECT_CODE).first():
            db.add(
                IssuingEntity(
                    code=SEED_PROJECT_CODE,
                    name_e="Seed Project",
                    name_p="Seed Project",
                    project_code=SEED_PROJECT_CODE,
                    is_active=True,
                    sort_order=20,
                )
            )
        if not db.query(IssuingEntity).filter(IssuingEntity.code == LEGACY_PROJECT_CODE).first():
            db.add(
                IssuingEntity(
                    code=LEGACY_PROJECT_CODE,
                    name_e="Legacy Test Project",
                    name_p="Legacy Test Project",
                    project_code=LEGACY_PROJECT_CODE,
                    is_active=True,
                    sort_order=30,
                )
            )

        if not db.query(CorrespondenceCategory).filter(CorrespondenceCategory.code == "CO").first():
            db.add(
                CorrespondenceCategory(
                    code="CO",
                    name_e="Correspondence",
                    name_p="Correspondence",
                    is_active=True,
                    sort_order=10,
                )
            )

        db.commit()

    yield
