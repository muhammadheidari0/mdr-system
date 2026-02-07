import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app
from app.core.security import get_password_hash
from app.db.models import User
from app.db.session import SessionLocal
from tests.auth_helpers import get_test_admin_credentials

client = TestClient(app)


def test_read_main():
    response = client.get("/")
    assert response.status_code == 200


def _login_and_get_token() -> str:
    email, password = get_test_admin_credentials()
    return _login_and_get_token_for(email, password)


def _login_and_get_token_for(email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200, response.text
    assert "access_token" in response.json()
    return response.json()["access_token"]


@pytest.fixture
def admin_token() -> str:
    return _login_and_get_token()


def _create_temp_user(password: str) -> str:
    email = f"pwchange-{uuid4().hex[:10]}@mdr.local"
    with SessionLocal() as db:
        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name="Password Test User",
            role="user",
            is_active=True,
        )
        db.add(user)
        db.commit()
    return email


def _delete_user_by_email(email: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if user:
            db.delete(user)
            db.commit()


def test_login_success(admin_token):
    assert isinstance(admin_token, str)
    assert len(admin_token) > 20


def test_protected_dashboard_without_token():
    response = client.get("/api/v1/dashboard/stats")
    assert response.status_code in [401, 403]


def test_protected_dashboard_with_token(admin_token):
    response = client.get(
        "/api/v1/dashboard/stats",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert "total" in response.json()


def test_login_wrong_credentials():
    email, password = get_test_admin_credentials()
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": f"{password}-wrong"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 401


def test_users_endpoint_without_admin_token():
    response = client.get("/api/v1/users/")
    assert response.status_code in [401, 403]


def test_users_endpoint_with_admin_token(admin_token):
    response = client.get(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_change_password_success_and_relogin():
    old_password = "OldPass#1234"
    new_password = "NewPass#1234"
    email = _create_temp_user(old_password)

    try:
        token = _login_and_get_token_for(email, old_password)
        response = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": old_password,
                "new_password": new_password,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("ok") is True

        old_login_response = client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": old_password},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert old_login_response.status_code == 401

        new_login_response = client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": new_password},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert new_login_response.status_code == 200
    finally:
        _delete_user_by_email(email)


def test_change_password_rejects_wrong_current_password():
    old_password = "OldPass#9876"
    email = _create_temp_user(old_password)

    try:
        token = _login_and_get_token_for(email, old_password)
        response = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "wrong-password",
                "new_password": "NewPass#9876",
            },
        )
        assert response.status_code == 400
        assert "detail" in response.json()

        # Ensure password remains unchanged.
        _ = _login_and_get_token_for(email, old_password)
    finally:
        _delete_user_by_email(email)


if __name__ == "__main__":
    print("Running API tests...")
    pytest.main([__file__, "-v"])
