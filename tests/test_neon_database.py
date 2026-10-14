"""Contratos pooled/direct e TLS, sem acesso a Neon ou Supabase reais."""

import runpy
from types import SimpleNamespace
from unittest.mock import MagicMock

import certifi
import pytest
from sqlalchemy import create_engine as real_create_engine
from sqlalchemy.pool import NullPool

from backend.app.core.config import Settings
from backend.app.core.database import Database, DatabaseConfigurationError

POOLED = "postgresql://synthetic_user:synthetic_password@ep-synthetic-pooler.us-east-2.aws.neon.tech/neondb"
DIRECT = "postgresql://synthetic_admin:synthetic_admin_password@ep-synthetic.us-east-2.aws.neon.tech/neondb"


@pytest.fixture
def engines(monkeypatch):
    calls = []
    created = []

    def capture(url, **kwargs):
        calls.append((url, kwargs))
        engine = real_create_engine(url, **kwargs)
        created.append(engine)
        return engine

    monkeypatch.setattr("backend.app.core.database.create_engine", capture)
    yield calls
    for engine in created:
        engine.dispose()


@pytest.mark.parametrize(
    "parameters",
    [
        "",
        "?sslmode=require",
        "?sslmode=verify-full",
        "?sslmode=require&channel_binding=require",
        "?channel_binding=require",
    ],
)
def test_neon_pooled_tls_is_always_verified_and_transaction_scoped(engines, parameters):
    database = Database(Settings(_env_file=None, database_url=POOLED + parameters))
    url, options = engines[0]
    assert url.drivername == "postgresql+psycopg"
    assert not url.query
    assert options["connect_args"]["sslmode"] == "verify-full"
    assert options["connect_args"]["prepare_threshold"] is None
    assert "options" not in options["connect_args"]
    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == 5
    assert options["max_overflow"] == 0
    assert options["pool_timeout"] == 5
    if "channel_binding" in parameters:
        assert options["connect_args"]["channel_binding"] == "require"
    connection = MagicMock()
    database.engine.dispatch.begin(connection)
    connection.exec_driver_sql.assert_called_once_with("SET LOCAL statement_timeout = 5000")


def test_migrations_use_only_direct_url_and_null_pool(engines):
    settings = Settings(
        _env_file=None,
        database_url=POOLED,
        database_migration_url=DIRECT + "?sslmode=require&channel_binding=require",
        database_migration_statement_timeout_ms=120000,
    )
    application = Database(settings)
    migration = Database.for_migrations(settings)
    app_url, _ = engines[0]
    migration_url, options = engines[1]
    assert app_url.host == "ep-synthetic-pooler.us-east-2.aws.neon.tech"
    assert migration_url.host == "ep-synthetic.us-east-2.aws.neon.tech"
    assert migration_url.username == "synthetic_admin"
    assert not migration_url.query
    assert isinstance(migration.engine.pool, NullPool)
    assert options["connect_args"]["sslmode"] == "verify-full"
    assert options["connect_args"]["options"] == "-c statement_timeout=120000"
    assert options["connect_args"]["channel_binding"] == "require"
    for field in ("pool_size", "pool_timeout", "max_overflow"):
        assert field not in options
    assert application.engine is not migration.engine


@pytest.mark.parametrize(
    "url",
    [
        POOLED,
        POOLED.replace("ep-synthetic-pooler", "EP-SYNTHETIC-POOLER"),
        "postgresql://user:password@region.pooler.supabase.com/db",
    ],
)
def test_alembic_rejects_pooler_before_any_connection(engines, url):
    with pytest.raises(DatabaseConfigurationError):
        Database.for_migrations(Settings(_env_file=None, database_migration_url=url))
    assert engines == []


@pytest.mark.parametrize("migration_url", [None, ""])
def test_alembic_never_falls_back_to_application_url(engines, migration_url):
    with pytest.raises(DatabaseConfigurationError) as error:
        Database.for_migrations(
            Settings(_env_file=None, database_url=DIRECT, database_migration_url=migration_url)
        )
    assert "BIOSAUDE_DATABASE_MIGRATION_URL" in str(error.value)
    assert "synthetic_admin_password" not in str(error.value)
    assert engines == []


def test_migration_credentials_do_not_enable_application_database(engines):
    database = Database(Settings(_env_file=None, database_migration_url=DIRECT))
    assert database.engine is None
    assert database.probe() is False
    assert engines == []


@pytest.mark.parametrize(
    "query",
    [
        "sslmode=disable",
        "sslmode=allow",
        "sslmode=prefer",
        "sslmode=verify-ca",
        "channel_binding=disable",
        "channel_binding=prefer",
        "host=other-host",
        "hostaddr=127.0.0.1",
        "sslrootcert=other-file",
        "sslcert=private-file",
        "options=-c%20statement_timeout%3D0",
        "connect_timeout=0",
        "sslmode=require&sslmode=disable",
        "sslmode=require&sslmode=require",
        "channel_binding=require&channel_binding=require",
        "sslmode=",
        "application_name=secret",
    ],
)
def test_unsafe_or_arbitrary_query_parameters_are_rejected_without_secrets(engines, query):
    for migration in (False, True):
        settings = Settings(
            _env_file=None,
            database_url=POOLED + "?" + query,
            database_migration_url=DIRECT + "?" + query,
        )
        with pytest.raises(DatabaseConfigurationError) as error:
            Database(settings, migration=migration)
        assert "synthetic" not in str(error.value)
        assert query not in str(error.value)
        assert error.value.__suppress_context__
    assert engines == []


@pytest.mark.parametrize("port", [0, 65536])
def test_invalid_ports_rejected(engines, port):
    with pytest.raises(DatabaseConfigurationError):
        Database(
            Settings(_env_file=None, database_url=POOLED.replace("/neondb", f":{port}/neondb"))
        )
    assert engines == []


def test_windows_default_uses_certifi_public_bundle(monkeypatch, engines):
    from pathlib import Path

    actual_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: False
        if str(path) == "/etc/ssl/certs/ca-certificates.crt"
        else actual_is_file(path),
    )
    Database(Settings(_env_file=None, database_url=POOLED))
    assert engines[0][1]["connect_args"]["sslrootcert"] == certifi.where()


def test_explicit_ca_override_preserved_and_missing_ca_rejected(tmp_path, engines):
    ca = tmp_path / "synthetic-ca.crt"
    ca.write_text("synthetic test certificate")
    Database(Settings(_env_file=None, database_url=POOLED, database_ssl_root_cert=str(ca)))
    assert engines[0][1]["connect_args"]["sslrootcert"] == str(ca)
    with pytest.raises(DatabaseConfigurationError):
        Database.for_migrations(
            Settings(
                _env_file=None,
                database_migration_url=DIRECT,
                database_ssl_root_cert=str(tmp_path / "missing.crt"),
            )
        )


def test_both_urls_load_independently_from_environment_and_stay_masked(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("BIOSAUDE_DATABASE_URL=not-used\nBIOSAUDE_DATABASE_MIGRATION_URL=not-used\n")
    monkeypatch.setenv("BIOSAUDE_DATABASE_URL", POOLED)
    monkeypatch.setenv("BIOSAUDE_DATABASE_MIGRATION_URL", DIRECT)
    settings = Settings(_env_file=dotenv)
    assert settings.database_url.get_secret_value() == POOLED
    assert settings.database_migration_url.get_secret_value() == DIRECT
    assert settings.catalog_enabled is False
    for secret in ("synthetic_password", "synthetic_admin_password"):
        assert secret not in repr(settings)
        assert secret not in settings.model_dump_json()


def test_alembic_environment_selects_migration_factory_and_preserves_metadata(monkeypatch):
    from alembic import context
    from alembic.config import Config

    monkeypatch.setattr(context, "config", Config(), raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: False)
    configure = MagicMock()
    monkeypatch.setattr(context, "configure", configure)
    monkeypatch.setattr(context, "begin_transaction", MagicMock())
    run = MagicMock()
    monkeypatch.setattr(context, "run_migrations", run)
    database = SimpleNamespace(engine=MagicMock(), dispose=MagicMock())
    factory = MagicMock(return_value=database)
    monkeypatch.setattr(Database, "for_migrations", factory)
    module = runpy.run_path("migrations/env.py")
    factory.assert_called_once()
    assert isinstance(factory.call_args.args[0], Settings)
    assert len(module["target_metadata"].tables) == 6
    assert configure.call_args.kwargs["target_metadata"] is module["target_metadata"]
    run.assert_called_once()
    database.dispose.assert_called_once()


def test_alembic_invalid_direct_configuration_fails_before_running_migrations(monkeypatch):
    from alembic import context
    from alembic.config import Config

    monkeypatch.setenv("BIOSAUDE_DATABASE_MIGRATION_URL", POOLED)
    monkeypatch.setattr(context, "config", Config(), raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: False)
    run = MagicMock()
    monkeypatch.setattr(context, "run_migrations", run)
    with pytest.raises(DatabaseConfigurationError):
        runpy.run_path("migrations/env.py")
    run.assert_not_called()


@pytest.mark.parametrize(
    "host",
    [
        "direct.example.invalid,ep-synthetic-pooler.us-east-2.aws.neon.tech",
        "direct.example.invalid hostaddr=127.0.0.1",
        "ep-synthetic%2Dpooler.example.invalid",
    ],
)
def test_ambiguous_hosts_cannot_bypass_direct_connection_validation(engines, host):
    url = "postgresql://synthetic_user:synthetic_password@" + host + "/neondb"
    with pytest.raises(DatabaseConfigurationError):
        Database.for_migrations(Settings(_env_file=None, database_migration_url=url))
    assert engines == []
