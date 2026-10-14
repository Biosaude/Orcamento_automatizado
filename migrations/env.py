"""Migrações PostgreSQL da plataforma Biosaúde."""

from logging.config import fileConfig

from alembic import context

from backend.app.core.config import Settings
from backend.app.core.database import Database
from backend.app.persistence import models as models
from backend.app.persistence.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# O import de models registra as seis tabelas na metadata, mesmo sem uso direto.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Não executar migrações offline sem configuração explícita."""
    raise RuntimeError(
        "Migrações offline não estão habilitadas. Utilize uma conexão PostgreSQL validada."
    )


def run_migrations_online() -> None:
    """Reutiliza a conexão PostgreSQL segura da aplicação."""
    database = Database.for_migrations(Settings())

    try:
        with database.engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        database.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
