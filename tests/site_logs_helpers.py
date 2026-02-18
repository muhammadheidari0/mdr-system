from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import UserDisciplineScope, UserProjectScope
from app.db.session import SessionLocal
from tests.auth_helpers import get_auth_headers


def admin_headers(client: TestClient) -> dict[str, str]:
    return get_auth_headers(client)


def ensure_project_discipline(client: TestClient, headers: dict[str, str]) -> tuple[str, str]:
    project_res = client.get("/api/v1/settings/projects", headers=headers)
    assert project_res.status_code == 200, project_res.text
    project_items = project_res.json().get("items", [])
    if not project_items:
        code = f"SLP{uuid4().hex[:4].upper()}"
        upsert = client.post(
            "/api/v1/settings/projects/upsert",
            json={"code": code, "name_e": f"Project {code}", "is_active": True},
            headers=headers,
        )
        assert upsert.status_code == 200, upsert.text
        project_code = code
    else:
        row = project_items[0]
        project_code = str(row.get("code") or row.get("project_code") or "").strip().upper()

    discipline_res = client.get("/api/v1/settings/disciplines", headers=headers)
    assert discipline_res.status_code == 200, discipline_res.text
    discipline_items = discipline_res.json().get("items", [])
    if not discipline_items:
        code = f"SLD{uuid4().hex[:3].upper()}"
        upsert = client.post(
            "/api/v1/settings/disciplines/upsert",
            json={"code": code, "name_e": f"Discipline {code}"},
            headers=headers,
        )
        assert upsert.status_code == 200, upsert.text
        discipline_code = code
    else:
        row = discipline_items[0]
        discipline_code = str(row.get("code") or row.get("discipline_code") or "").strip().upper()

    assert project_code
    assert discipline_code
    return project_code, discipline_code


def ensure_org(client: TestClient, headers: dict[str, str], *, org_type: str, code_prefix: str) -> int:
    list_res = client.get("/api/v1/settings/organizations", headers=headers)
    assert list_res.status_code == 200, list_res.text
    items = list_res.json().get("items", [])
    existing = next((x for x in items if str(x.get("org_type") or "").strip().lower() == org_type.lower()), None)
    if existing:
        return int(existing.get("id") or 0)

    code = f"{code_prefix}_{uuid4().hex[:5].upper()}"
    upsert = client.post(
        "/api/v1/settings/organizations/upsert",
        json={"code": code, "name": f"{org_type.title()} {code}", "org_type": org_type, "is_active": True},
        headers=headers,
    )
    assert upsert.status_code == 200, upsert.text
    return int(upsert.json().get("item", {}).get("id") or 0)


def create_scoped_user_and_login(
    client: TestClient,
    admin: dict[str, str],
    *,
    org_type: str,
    project_code: str,
    discipline_code: str,
    email_prefix: str,
) -> dict[str, str | int]:
    organization_id = ensure_org(client, admin, org_type=org_type, code_prefix=email_prefix.upper())
    assert organization_id > 0

    email = f"{email_prefix}_{uuid4().hex[:8]}@mdr.local"
    password = f"Pwd!{uuid4().hex[:10]}"
    create_res = client.post(
        "/api/v1/users/",
        json={
            "email": email,
            "password": password,
            "full_name": email_prefix.title(),
            "role": "user",
            "organization_id": organization_id,
            "organization_role": "viewer",
            "is_active": True,
        },
        headers=admin,
    )
    assert create_res.status_code == 200, create_res.text
    user_id = int(create_res.json().get("id") or 0)
    assert user_id > 0

    with SessionLocal() as db:
        has_project_scope = (
            db.query(UserProjectScope.id)
            .filter(UserProjectScope.user_id == user_id, UserProjectScope.project_code == str(project_code).upper())
            .first()
        )
        if not has_project_scope:
            db.add(UserProjectScope(user_id=user_id, project_code=str(project_code).upper()))

        has_discipline_scope = (
            db.query(UserDisciplineScope.id)
            .filter(
                UserDisciplineScope.user_id == user_id,
                UserDisciplineScope.discipline_code == str(discipline_code).upper(),
            )
            .first()
        )
        if not has_discipline_scope:
            db.add(UserDisciplineScope(user_id=user_id, discipline_code=str(discipline_code).upper()))
        db.commit()

    login_res = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert login_res.status_code == 200, login_res.text
    token = str(login_res.json().get("access_token") or "").strip()
    assert token

    return {
        "email": email,
        "password": password,
        "user_id": user_id,
        "organization_id": organization_id,
        "headers": {"Authorization": f"Bearer {token}"},
    }
