"""Ponto de entrada da API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.catalog import router as catalog_router
from backend.app.api.health import router
from backend.app.core.auth import TokenVerifier
from backend.app.core.config import Settings
from backend.app.core.database import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(resolved_settings)
        app.state.database = database
        try:
            yield
        finally:
            database.dispose()

    app = FastAPI(
        title="Biosaúde OPME",
        version="0.1.0",
        description="MVP com conexão PostgreSQL opcional. Fluxos operacionais não implementados.",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.token_verifier = TokenVerifier(resolved_settings)
    app.include_router(router)
    app.include_router(catalog_router)
    return app


app = create_app()
