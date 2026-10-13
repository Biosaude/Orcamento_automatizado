"""Ponto de entrada da API."""

from fastapi import FastAPI

from backend.app.api.health import router
from backend.app.core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="Biosaúde OPME",
        version="0.1.0",
        description="Estrutura inicial do MVP. Integrações e envio não implementados.",
    )
    app.state.settings = settings if settings is not None else Settings()
    app.include_router(router)
    return app


app = create_app()
