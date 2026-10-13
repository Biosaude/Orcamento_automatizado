"""Tokens Supabase Auth assinados; vínculos e permissões vêm do banco."""

from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.core.database import get_session
from backend.app.domain.models import UserRole
from backend.app.persistence.models import CompanyORM, UserORM

bearer = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    return HTTPException(401, "Autenticação inválida", headers={"WWW-Authenticate": "Bearer"})


class TokenVerifier:
    def __init__(self, settings: Settings):
        self.jwks: PyJWKClient | None = None
        self.issuer = ""
        if settings.supabase_url:
            parsed = urlsplit(settings.supabase_url)
            if (
                parsed.scheme == "https"
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not parsed.query
                and not parsed.fragment
                and parsed.path in {"", "/"}
            ):
                self.issuer = settings.supabase_url.rstrip("/") + "/auth/v1"
                self.jwks = PyJWKClient(
                    self.issuer + "/.well-known/jwks.json", timeout=5, lifespan=300
                )

    def verify(self, token: str) -> str:
        if self.jwks is None:
            raise HTTPException(503, "Autenticação indisponível")
        if len(token) > 8192:
            raise unauthorized()
        try:
            # Não usar jku/issuer enviados pelo cliente para escolher destino ou chave.
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in {"ES256", "RS256"} or not header.get("kid"):
                raise unauthorized()
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
                issuer=self.issuer,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
            subject = str(UUID(claims["sub"]))
            if claims.get("role") != "authenticated":
                raise unauthorized()
            return subject
        except PyJWKClientConnectionError:
            raise HTTPException(503, "Autenticação indisponível") from None
        except (jwt.PyJWTError, PyJWKClientError, ValueError, TypeError, KeyError):
            raise unauthorized() from None


def authenticated_subject(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None:
        raise unauthorized()
    return request.app.state.token_verifier.verify(credentials.credentials)


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    company_id: UUID
    role: UserRole


def current_principal(
    subject: Annotated[str, Depends(authenticated_subject)],
    session: Annotated[Session, Depends(get_session)],
    company_id: Annotated[UUID | None, Header(alias="X-Company-ID")] = None,
) -> Principal:
    query = (
        select(UserORM)
        .join(CompanyORM)
        .where(UserORM.identity_subject == subject, CompanyORM.active.is_(True))
    )
    if company_id is not None:
        # Seletor de vínculo, não fonte de autorização: sempre condicionado ao sub verificado.
        query = query.where(UserORM.company_id == company_id)
    memberships = session.scalars(query.limit(2)).all()
    if len(memberships) != 1:
        raise HTTPException(403, "Vínculo empresarial ausente ou ambíguo")
    membership = memberships[0]
    try:
        role = UserRole(membership.role)
    except ValueError:
        raise HTTPException(403, "Perfil sem permissão") from None
    return Principal(membership.id, membership.company_id, role)


def catalog_writer(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    if principal.role not in {UserRole.ADMINISTRATOR, UserRole.OPERATOR}:
        raise HTTPException(403, "Perfil sem permissão")
    return principal
