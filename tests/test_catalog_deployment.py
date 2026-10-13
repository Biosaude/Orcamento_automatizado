from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def test_catalog_disabled_by_default_even_with_auth_provider_configured():
    settings = Settings(_env_file=None, supabase_url="https://synthetic-auth.supabase.co")
    with TestClient(create_app(settings)) as client:
        for path in ("/api/v1/hospitals", "/api/v1/products", "/api/v1/auth/me"):
            assert client.get(path).status_code == 404
            assert client.post(path, json={}).status_code == 404
        paths = client.get("/openapi.json").json()["paths"]
        assert not any(path.startswith("/api/v1/") for path in paths)
        assert client.get("/health").status_code == 200
        assert client.get("/health/database").status_code == 403


def test_explicit_catalog_enablement_still_requires_authentication(monkeypatch):
    monkeypatch.setenv("BIOSAUDE_CATALOG_ENABLED", "true")
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/api/v1/products").status_code == 401
        assert client.post("/api/v1/hospitals", json={"name": "Synthetic"}).status_code == 401
        assert client.get("/health").status_code == 200
