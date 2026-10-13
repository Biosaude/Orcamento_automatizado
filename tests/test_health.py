from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def test_health_reports_only_local_runtime_health():
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "biosaude-opme-automation",
        "version": "0.1.0",
        "environment": "test",
        "external_integrations": "disabled",
    }


def test_no_operational_endpoints_exist():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        for path in ("/quotes", "/send", "/approve", "/products"):
            assert client.post(path, json={}).status_code == 404


def test_configured_credentials_are_never_exposed_by_health():
    settings = Settings(_env_file=None, openai_api_key="synthetic-test-value")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    assert "synthetic-test-value" not in response.text
    assert response.json()["external_integrations"] == "disabled"
