"""Saúde do processo HTTP; não representa disponibilidade de serviços externos."""

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "biosaude-opme-automation"
    version: str = "0.1.0"
    environment: str
    external_integrations: Literal["disabled"] = "disabled"


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health(request: Request) -> HealthResponse:
    return HealthResponse(environment=request.app.state.settings.environment)


@router.get("/health/database", tags=["health"], responses={503: {"description": "Indisponível"}})
def database_health(request: Request) -> JSONResponse:
    ready = request.app.state.database.probe()
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ok" if ready else "unavailable"},
    )
