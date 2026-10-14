"""PostgreSQL/psycopg: configuração lazy, sem DDL ou commits automáticos."""

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import certifi
from fastapi import HTTPException, Request
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from backend.app.core.config import Settings


class DatabaseConfigurationError(ValueError):
    """Erro seguro: não inclui URL, senha ou exceção original."""


class Database:
    @classmethod
    def for_migrations(cls, settings: Settings) -> "Database":
        """Somente URL direta explícita; nunca usa credenciais operacionais como fallback."""
        return cls(settings, migration=True)

    def __init__(self, settings: Settings, *, migration: bool = False):
        self.engine: Engine | None = None
        self.sessions: sessionmaker[Session] | None = None
        secret_url = settings.database_migration_url if migration else settings.database_url
        if secret_url is None or not secret_url.get_secret_value():
            if migration:
                raise DatabaseConfigurationError(
                    "BIOSAUDE_DATABASE_MIGRATION_URL direta é obrigatória para Alembic."
                )
            return
        try:
            url = make_url(secret_url.get_secret_value())
            allowed_query = {"sslmode": {"require", "verify-full"}, "channel_binding": {"require"}}
            parsed = urlsplit(secret_url.get_secret_value())
            pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
            ca_file = settings.database_ssl_root_cert or (
                "/etc/ssl/certs/ca-certificates.crt"
                if Path("/etc/ssl/certs/ca-certificates.crt").is_file()
                else certifi.where()
            )
            if (
                url.drivername not in {"postgresql", "postgresql+psycopg"}
                or not all((url.host, url.username, url.password, url.database))
                or any(char.isspace() or char in ",/%\\" for char in (url.host or ""))
                or any(
                    key not in allowed_query or value not in allowed_query[key]
                    for key, value in pairs
                )
                or len({key for key, _ in pairs}) != len(pairs)
                or parsed.fragment
                or (url.port is not None and not 1 <= url.port <= 65535)
                or not Path(ca_file).is_file()
            ):
                raise ValueError
            hostname = url.host.lower().rstrip(".")
            pooled = hostname.split(".")[0].endswith("-pooler") or hostname.endswith(
                ".pooler.supabase.com"
            )
            if migration and pooled:
                raise ValueError
            channel_binding = url.query.get("channel_binding")
            # Parâmetros de confiança nunca ficam na URL passada ao driver.
            url = url.set(drivername="postgresql+psycopg", query={})
        except (ValueError, SQLAlchemyError, OSError):
            raise DatabaseConfigurationError(
                "Configuração PostgreSQL inválida; consulte docs/database.md."
            ) from None
        timeout = (
            settings.database_migration_statement_timeout_ms
            if migration
            else settings.database_statement_timeout_ms
        )
        connect_args = {
            "sslmode": "verify-full",
            "sslrootcert": ca_file,
            "connect_timeout": settings.database_connect_timeout,
            "prepare_threshold": None,
        }
        if channel_binding is not None:
            connect_args["channel_binding"] = channel_binding
        # PgBouncer transaction pooling não depende de parâmetros de sessão persistentes.
        if not pooled:
            connect_args["options"] = f"-c statement_timeout={timeout}"
        pool_options = (
            {"poolclass": NullPool}
            if migration
            else {
                "pool_size": settings.database_pool_size,
                "max_overflow": settings.database_max_overflow,
                "pool_timeout": settings.database_pool_timeout,
            }
        )
        self.engine = create_engine(
            url,
            echo=False,
            hide_parameters=True,
            pool_pre_ping=True,
            connect_args=connect_args,
            **pool_options,
        )
        if pooled:

            @event.listens_for(self.engine, "begin")
            def set_transaction_timeout(connection):
                connection.exec_driver_sql(f"SET LOCAL statement_timeout = {timeout}")

        self.sessions = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def probe(self) -> bool:
        """Somente SELECT 1. Nunca inspeciona dados ou altera o schema."""
        if self.engine is None:
            return False
        try:
            with self.engine.connect() as connection:
                return connection.execute(text("SELECT 1")).scalar_one() == 1
        except SQLAlchemyError:
            # Exceções do driver podem conter dados sensíveis: não registrar detalhes.
            return False

    def dispose(self) -> None:
        if self.engine is not None:
            self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    """Uma sessão por requisição; fechamento/rollback, nunca commit implícito."""
    database: Database = request.app.state.database
    if database.sessions is None:
        raise HTTPException(status_code=503, detail="Banco indisponível")
    with database.sessions() as session:
        try:
            yield session
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="Banco indisponível") from None
