"""Modelos iniciais sem dados reais, fórmulas financeiras ou acesso a serviços.

company_id prepara o escopo de dados; não substitui autorização nem RLS no banco.
"""

from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Company(DomainModel):
    id: UUID
    name: str = Field(min_length=1)
    active: bool = True


class CompanyScopedModel(DomainModel):
    id: UUID
    company_id: UUID


class UserRole(StrEnum):
    ADMINISTRATOR = "administrator"
    REVIEWER = "reviewer"
    OPERATOR = "operator"


class User(CompanyScopedModel):
    display_name: str = Field(min_length=1)
    role: UserRole
    identity_subject: str | None = None


class Product(CompanyScopedModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    manufacturer: str | None = None


class QuoteTemplate(StrEnum):
    STANDARD_VS_OPME = "standard_vs_opme"
    SAO_CAMILO = "sao_camilo"


class Hospital(CompanyScopedModel):
    name: str = Field(min_length=1)
    quote_template: QuoteTemplate = QuoteTemplate.STANDARD_VS_OPME
    official_table_id: str | None = None


class RequestStatus(StrEnum):
    RECEIVED = "received"
    UNDER_HUMAN_REVIEW = "under_human_review"


class QuoteRequest(CompanyScopedModel):
    hospital_id: UUID
    reference: str = Field(min_length=1)
    status: RequestStatus = RequestStatus.RECEIVED
    original_email_message_id: str | None = None
    original_email_thread_id: str | None = None


class QuoteItem(CompanyScopedModel):
    request_id: UUID
    product_id: UUID
    quantity: int = Field(gt=0, strict=True)
    # Preço informado; nenhum preço ou total é calculado nesta etapa.
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
