"""PostgreSQL/psycopg: configuração lazy, sem DDL ou commits automáticos."""

from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException, Request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import Settings


class DatabaseConfigurationError(ValueError):
    """Erro seguro: não inclui URL, senha ou exceção original."""


class Database:
    def __init__(self, settings: Settings):
        self.engine: Engine | None = None
        self.sessions: sessionmaker[Session] | None = None
        if settings.database_url is None or not settings.database_url.get_secret_value():
            return
        try:
            url = make_url(settings.database_url.get_secret_value())
            if (
                url.drivername not in {"postgresql", "postgresql+psycopg"}
                or not all((url.host, url.username, url.password, url.database))
                or url.query
                or not Path(settings.database_ssl_root_cert).is_file()
            ):
                raise ValueError
            url = url.set(drivername="postgresql+psycopg")
        except (ValueError, SQLAlchemyError, OSError):
            raise DatabaseConfigurationError(
                "Configuração PostgreSQL inválida; consulte docs/database.md."
            ) from None
        self.engine = create_engine(
            url,
            echo=False,
            hide_parameters=True,
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            connect_args={
                "sslmode": "verify-full",
                "sslrootcert": settings.database_ssl_root_cert,
                "connect_timeout": settings.database_connect_timeout,
                "options": f"-c statement_timeout={settings.database_statement_timeout_ms}",
                # Compatível com o transaction pooler; não manter prepared statements.
                "prepare_threshold": None,
            },
        )
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
