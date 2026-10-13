"""Cadastros autenticados com escopo obrigatório em cada operação."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.catalog_schemas import (
    HospitalInput,
    HospitalResponse,
    ProductInput,
    ProductResponse,
)
from backend.app.core.auth import Principal, catalog_writer, current_principal
from backend.app.core.database import get_session
from backend.app.persistence.models import CompanyORM, HospitalORM, ProductORM

router = APIRouter(prefix="/api/v1", tags=["catalog"])
Reader = Annotated[Principal, Depends(current_principal)]
Writer = Annotated[Principal, Depends(catalog_writer)]
DB = Annotated[Session, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100000)]


@router.get("/auth/me")
def me(principal: Reader) -> Principal:
    return principal


def lock_company(session: Session, principal: Principal) -> None:
    # Serializa mutations da mesma empresa, inclusive a verificação de duplicidade
    # de hospitais (o schema existente não tem UNIQUE por nome).
    active = session.scalar(
        select(CompanyORM.id)
        .where(CompanyORM.id == principal.company_id, CompanyORM.active.is_(True))
        .with_for_update()
    )
    if active is None:
        raise HTTPException(403, "Empresa indisponível")


def find(session: Session, principal: Principal, model, entity_id: UUID):
    entity = session.scalar(
        select(model).where(model.id == entity_id, model.company_id == principal.company_id)
    )
    if entity is None:
        # Mesmo resultado para inexistente e pertencente a outra empresa.
        raise HTTPException(404, "Cadastro não encontrado")
    return entity


def ensure_unique(session: Session, principal: Principal, model, field, value, entity_id=None):
    query = select(model.id).where(
        model.company_id == principal.company_id,
        func.lower(func.trim(field)) == value.strip().lower(),
    )
    if entity_id is not None:
        query = query.where(model.id != entity_id)
    if session.scalar(query.limit(1)) is not None:
        raise HTTPException(409, "Cadastro duplicado")


def save(session: Session, entity):
    session.add(entity)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Conflito no cadastro") from None
    return entity


@router.post("/hospitals", response_model=HospitalResponse, status_code=201)
def create_hospital(payload: HospitalInput, principal: Writer, session: DB):
    lock_company(session, principal)
    ensure_unique(session, principal, HospitalORM, HospitalORM.name, payload.name)
    return save(session, HospitalORM(company_id=principal.company_id, **payload.model_dump()))


@router.get("/hospitals", response_model=list[HospitalResponse])
def list_hospitals(principal: Reader, session: DB, limit: Limit = 50, offset: Offset = 0):
    return session.scalars(
        select(HospitalORM)
        .where(HospitalORM.company_id == principal.company_id)
        .order_by(HospitalORM.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.get("/hospitals/{entity_id}", response_model=HospitalResponse)
def get_hospital(entity_id: UUID, principal: Reader, session: DB):
    return find(session, principal, HospitalORM, entity_id)


@router.put("/hospitals/{entity_id}", response_model=HospitalResponse)
def update_hospital(entity_id: UUID, payload: HospitalInput, principal: Writer, session: DB):
    lock_company(session, principal)
    entity = find(session, principal, HospitalORM, entity_id)
    ensure_unique(session, principal, HospitalORM, HospitalORM.name, payload.name, entity_id)
    for field, value in payload.model_dump().items():
        setattr(entity, field, value)
    return save(session, entity)


@router.post("/products", response_model=ProductResponse, status_code=201)
def create_product(payload: ProductInput, principal: Writer, session: DB):
    lock_company(session, principal)
    ensure_unique(session, principal, ProductORM, ProductORM.code, payload.code)
    return save(session, ProductORM(company_id=principal.company_id, **payload.model_dump()))


@router.get("/products", response_model=list[ProductResponse])
def list_products(principal: Reader, session: DB, limit: Limit = 50, offset: Offset = 0):
    return session.scalars(
        select(ProductORM)
        .where(ProductORM.company_id == principal.company_id)
        .order_by(ProductORM.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.get("/products/{entity_id}", response_model=ProductResponse)
def get_product(entity_id: UUID, principal: Reader, session: DB):
    return find(session, principal, ProductORM, entity_id)


@router.put("/products/{entity_id}", response_model=ProductResponse)
def update_product(entity_id: UUID, payload: ProductInput, principal: Writer, session: DB):
    lock_company(session, principal)
    entity = find(session, principal, ProductORM, entity_id)
    ensure_unique(session, principal, ProductORM, ProductORM.code, payload.code, entity_id)
    for field, value in payload.model_dump().items():
        setattr(entity, field, value)
    return save(session, entity)
