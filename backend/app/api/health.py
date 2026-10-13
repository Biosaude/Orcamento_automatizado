"""Saúde do processo HTTP; não representa disponibilidade de serviços externos."""

from typing import Literal

from fastapi import APIRouter, Request
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
