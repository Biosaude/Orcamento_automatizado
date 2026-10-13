from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend.app.core.config import Settings
from backend.app.core.database import Database, DatabaseConfigurationError, get_session
from backend.app.main import create_app

URL = "postgresql://synthetic_user:synthetic_password@127.0.0.1:1/synthetic_db"
HEALTH_TOKEN = "synthetic-health-token"
HEALTH_HEADERS = {"X-Database-Health-Token": HEALTH_TOKEN}


def configured(**kwargs):
    return Settings(_env_file=None, database_url=URL, **kwargs)

def test_no_configuration_never_creates_engine(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr("backend.app.core.database.create_engine", factory)
    database = Database(Settings(_env_file=None))
    assert database.probe() is False
    database.dispose()
    factory.assert_not_called()



def test_engine_uses_verified_tls_bounded_pool_and_psycopg(
    monkeypatch, tmp_path
):
    ca_file = tmp_path / "synthetic-ca.crt"
    ca_file.write_text("synthetic-test-certificate", encoding="utf-8")

    factory = MagicMock()
    monkeypatch.setattr(
        "backend.app.core.database.create_engine",
        factory,
    )

    database = Database(
        configured(database_ssl_root_cert=str(ca_file))
    )

    args, options = factory.call_args

    assert args[0].drivername == "postgresql+psycopg"
    assert "synthetic_password" not in repr(args[0])

    assert options["connect_args"] == {
        "sslmode": "verify-full",
        "sslrootcert": str(ca_file),
        "connect_timeout": 5,
        "options": "-c statement_timeout=5000",
        "prepare_threshold": None,
    }

    assert options["echo"] is False
    assert options["hide_parameters"] is True
    assert options["pool_pre_ping"] is True
    assert options["max_overflow"] == 0

    factory.return_value.connect.assert_not_called()

    database.dispose()
    factory.return_value.dispose.assert_called_once()



@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///file.db",
        "postgresql+psycopg2://user:password@host/db",
        "malformed-synthetic-secret",
        "postgresql://user@host/db",
        URL + "?sslmode=disable",
        URL + "?host=other-host",
    ],
)
def test_invalid_urls_rejected_without_disclosing_input(url):
    with pytest.raises(DatabaseConfigurationError) as error:
        Database(Settings(_env_file=None, database_url=url))
    assert url not in str(error.value)
    assert error.value.__suppress_context__


def test_missing_ca_is_rejected():
    with pytest.raises(DatabaseConfigurationError):
        Database(configured(database_ssl_root_cert="/nonexistent/synthetic-ca.crt"))



def test_real_driver_handles_unreachable_database_without_exposing_details(
    tmp_path
):
    ca_file = tmp_path / "synthetic-ca.crt"
    ca_file.write_text("synthetic-test-certificate", encoding="utf-8")

    database = Database(
        configured(
            database_connect_timeout=1,
            database_ssl_root_cert=str(ca_file),
        )
    )

    try:
        assert database.engine.dialect.driver == "psycopg"
        assert database.probe() is False
    finally:
        database.dispose()



def test_probe_executes_only_select_and_closes_connection():
    database = Database(Settings(_env_file=None))
    database.engine = MagicMock()
    connection = database.engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 1
    assert database.probe() is True
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"
    connection.execute.assert_called_once()
    database.engine.connect.return_value.__exit__.assert_called_once()


def test_probe_failure_returns_generic_status():
    with TestClient(
        create_app(Settings(_env_file=None, database_health_token=HEALTH_TOKEN))
    ) as client:
        database = client.app.state.database
        database.engine = MagicMock()
        database.engine.connect.side_effect = OperationalError(
            "synthetic-secret-sql", {}, Exception("synthetic-password")
        )
        response = client.get("/health/database", headers=HEALTH_HEADERS)
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert "synthetic" not in response.text
        assert client.get("/health").status_code == 200


def test_database_health_success_and_shutdown():
    with TestClient(
        create_app(Settings(_env_file=None, database_health_token=HEALTH_TOKEN))
    ) as client:
        engine = MagicMock()
        client.app.state.database.engine = engine
        connection = engine.connect.return_value.__enter__.return_value
        connection.execute.return_value.scalar_one.return_value = 1
        assert client.get("/health/database", headers=HEALTH_HEADERS).json() == {"status": "ok"}
        assert client.get("/health/database", headers=HEALTH_HEADERS).status_code == 200
    engine.dispose.assert_called_once()


@pytest.mark.parametrize(
    "configured_token,headers",
    [
        (None, {}),
        (None, HEALTH_HEADERS),
        ("", HEALTH_HEADERS),
        (HEALTH_TOKEN, {}),
        (HEALTH_TOKEN, {"X-Database-Health-Token": "wrong-synthetic-token"}),
        (HEALTH_TOKEN, {"X-Forwarded-For": "127.0.0.1"}),
    ],
)
def test_database_health_denies_unauthorized_requests_without_probing(configured_token, headers):
    with TestClient(
        create_app(Settings(_env_file=None, database_health_token=configured_token))
    ) as client:
        probe = MagicMock()
        client.app.state.database.probe = probe
        response = client.get("/health/database", headers=headers)
        assert response.status_code == 403
        assert response.json() == {"detail": "Acesso negado"}
        probe.assert_not_called()
        assert client.get("/health").status_code == 200


def test_authorized_database_health_reports_unconfigured_database():
    with TestClient(
        create_app(Settings(_env_file=None, database_health_token=HEALTH_TOKEN))
    ) as client:
        response = client.get("/health/database", headers=HEALTH_HEADERS)
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert HEALTH_TOKEN not in response.text


def test_health_token_is_masked_and_service_role_setting_remains_compatible(monkeypatch):
    monkeypatch.setenv("BIOSAUDE_DATABASE_HEALTH_TOKEN", HEALTH_TOKEN)
    monkeypatch.setenv("BIOSAUDE_SUPABASE_SERVICE_ROLE_KEY", "synthetic-legacy-key")
    settings = Settings(_env_file=None)
    assert settings.database_health_token.get_secret_value() == HEALTH_TOKEN
    assert settings.supabase_service_role_key.get_secret_value() == "synthetic-legacy-key"
    for secret in (HEALTH_TOKEN, "synthetic-legacy-key"):
        assert secret not in repr(settings)
        assert secret not in settings.model_dump_json()


def test_environment_example_does_not_suggest_service_role_key():
    from pathlib import Path

    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
    assert "BIOSAUDE_SUPABASE_SERVICE_ROLE_KEY" not in example


def test_session_closes_without_automatic_commit_even_on_error():
    database = Database(Settings(_env_file=None))
    factory = MagicMock()
    database.sessions = factory
    session = factory.return_value.__enter__.return_value
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=database)))
    dependency = get_session(request)
    assert next(dependency) is session
    with pytest.raises(StopIteration):
        next(dependency)
    session.commit.assert_not_called()
    factory.return_value.__exit__.assert_called_once()
    factory.reset_mock()
    dependency = get_session(request)
    next(dependency)
    with pytest.raises(HTTPException) as error:
        dependency.throw(OperationalError("secret", {}, Exception("password")))
    assert error.value.status_code == 503
    assert error.value.detail == "Banco indisponível"
    factory.return_value.__exit__.assert_called_once()
    session.commit.assert_not_called()


def test_unconfigured_session_is_unavailable():
    database = Database(Settings(_env_file=None))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=database)))
    with pytest.raises(HTTPException) as error:
        next(get_session(request))
    assert error.value.status_code == 503


def test_database_settings_from_environment_mask_url_and_override_dotenv(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("BIOSAUDE_DATABASE_URL=not-used\n", encoding="utf-8")
    monkeypatch.setenv("BIOSAUDE_DATABASE_URL", URL)
    monkeypatch.setenv("BIOSAUDE_DATABASE_POOL_SIZE", "2")
    settings = Settings(_env_file=dotenv)
    assert settings.database_url.get_secret_value() == URL
    assert settings.database_pool_size == 2
    assert "synthetic_password" not in repr(settings)
    assert "synthetic_password" not in settings.model_dump_json()


@pytest.mark.parametrize(
    "field,value",
    [
        ("database_connect_timeout", 0),
        ("database_pool_size", 21),
        ("database_statement_timeout_ms", 0),
        ("database_max_overflow", -1),
    ],
)
def test_database_resource_limits_are_validated(field, value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        configured(**{field: value})
