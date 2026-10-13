"""Interfaces sem implementação: nenhuma persistência ou simulação está operacional."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from backend.app.domain.models import Company, CompanyScopedModel, DomainModel


class CompanyRepository(Protocol):
    """Acesso às empresas deverá exigir autorização administrativa explícita."""

    def get(self, company_id: UUID) -> Company | None: ...


class TenantRepository[T: CompanyScopedModel](Protocol):
    """Futuro adaptador deve filtrar por empresa e rejeitar save de outro escopo.

    Aplicável a User, Product, Hospital, QuoteRequest e QuoteItem. Não confiar em
    company_id recebido do cliente: obtê-lo da identidade autenticada no servidor.
    """

    def get(self, *, company_id: UUID, entity_id: UUID) -> T | None: ...

    def list(self, *, company_id: UUID, limit: int = 100) -> Sequence[T]: ...

    def save(self, *, company_id: UUID, entity: T) -> None: ...


class OfficialSimulationResult(DomainModel):
    """Contrato futuro: resultados deverão incluir a versão do simulador oficial."""

    simulator_version: str
    total: Decimal


class OfficialFinancialEngine(Protocol):
    """Implementar somente depois de receber e validar o simulador Biosaúde.

    A entrada é deliberadamente não especificada até análise do documento oficial.
    Não existe fórmula, cálculo substituto ou chamada à IA neste contrato.
    """

    def simulate(
        self, *, company_id: UUID, official_inputs: Mapping[str, object]
    ) -> OfficialSimulationResult: ...
