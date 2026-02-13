from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_legacy_tests_package_api_module_smoke() -> None:
    """
    Keep this module active so `pytest tests` does not hide skipped placeholders.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True
