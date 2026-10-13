"""Contratos HTTP de cadastro; escopo empresarial não é aceito na entrada."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.models import QuoteTemplate


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HospitalInput(InputModel):
    name: str = Field(min_length=1, max_length=255)
    quote_template: QuoteTemplate = QuoteTemplate.STANDARD_VS_OPME
    official_table_id: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def require_official_table(self):
        if self.quote_template == QuoteTemplate.SAO_CAMILO and not self.official_table_id:
            raise ValueError("Modelo São Camilo exige identificador da tabela oficial")
        return self


class ProductInput(InputModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=500)
    manufacturer: str | None = Field(default=None, min_length=1, max_length=255)


class HospitalResponse(HospitalInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID


class ProductResponse(ProductInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID
