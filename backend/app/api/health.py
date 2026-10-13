"""Saúde do processo HTTP; não representa disponibilidade de serviços externos."""

from secrets import compare_digest
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

router = APIRouter()
database_health_header = APIKeyHeader(name="X-Database-Health-Token", auto_error=False)


def authorize_database_health(
    request: Request,
    token: Annotated[str | None, Depends(database_health_header)],
) -> None:
    configured = request.app.state.settings.database_health_token
    expected = configured.get_secret_value() if configured is not None else ""
    if not expected or token is None or not compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Acesso negado")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "biosaude-opme-automation"
    version: str = "0.1.0"
    environment: str
    external_integrations: Literal["disabled"] = "disabled"


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health(request: Request) -> HealthResponse:
    return HealthResponse(environment=request.app.state.settings.environment)


@router.get(
    "/health/database",
    tags=["health"],
    dependencies=[Depends(authorize_database_health)],
    responses={403: {"description": "Acesso negado"}, 503: {"description": "Indisponível"}},
)
def database_health(request: Request) -> JSONResponse:
    ready = request.app.state.database.probe()
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ok" if ready else "unavailable"},
    )
