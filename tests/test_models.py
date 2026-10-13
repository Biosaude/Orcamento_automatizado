from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.domain.models import (
    Company,
    Hospital,
    Product,
    QuoteItem,
    QuoteRequest,
    QuoteTemplate,
    User,
    UserRole,
)

# Identificadores sintéticos exclusivos dos testes; não representam registros operacionais.
ENTITY_ID = UUID(int=1)
COMPANY_ID = UUID(int=2)
RELATED_ID = UUID(int=3)


@pytest.mark.parametrize(
    ("model", "fields"),
    [
        (User, {"display_name": "Test", "role": UserRole.REVIEWER}),
        (Product, {"code": "TEST", "name": "Test"}),
        (Hospital, {"name": "Test"}),
        (QuoteRequest, {"hospital_id": RELATED_ID, "reference": "TEST"}),
        (QuoteItem, {"request_id": RELATED_ID, "product_id": RELATED_ID, "quantity": 1}),
    ],
)
def test_tenant_entities_require_company_context(model, fields):
    with pytest.raises(ValidationError):
        model(id=ENTITY_ID, **fields)
    entity = model(id=ENTITY_ID, company_id=COMPANY_ID, **fields)
    assert entity.company_id == COMPANY_ID


def test_company_is_separate_from_tenant_entities():
    assert Company(id=COMPANY_ID, name="Synthetic test company").id == COMPANY_ID


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True])
def test_quote_item_rejects_invalid_quantities(quantity):
    with pytest.raises(ValidationError):
        QuoteItem(
            id=ENTITY_ID,
            company_id=COMPANY_ID,
            request_id=RELATED_ID,
            product_id=RELATED_ID,
            quantity=quantity,
        )


def test_quote_item_preserves_decimal_price_without_calculating_total():
    item = QuoteItem(
        id=ENTITY_ID,
        company_id=COMPANY_ID,
        request_id=RELATED_ID,
        product_id=RELATED_ID,
        quantity=2,
        unit_price="12.34",
    )
    assert item.unit_price == Decimal("12.34")
    assert "total" not in type(item).model_fields


def test_hospital_defaults_to_standard_and_allows_explicit_exception():
    standard = Hospital(id=ENTITY_ID, company_id=COMPANY_ID, name="Synthetic hospital")
    assert standard.quote_template == QuoteTemplate.STANDARD_VS_OPME
    exception = standard.model_copy(
        update={"quote_template": QuoteTemplate.SAO_CAMILO, "official_table_id": "test-table"}
    )
    assert exception.quote_template == QuoteTemplate.SAO_CAMILO
    assert exception.official_table_id == "test-table"


def test_request_can_preserve_email_thread_without_patient_fields():
    request = QuoteRequest(
        id=ENTITY_ID,
        company_id=COMPANY_ID,
        hospital_id=RELATED_ID,
        reference="TEST",
        original_email_message_id="synthetic-message",
        original_email_thread_id="synthetic-thread",
    )
    assert request.original_email_message_id == "synthetic-message"
    with pytest.raises(ValidationError):
        QuoteRequest(**request.model_dump(), patient_name="Forbidden test field")
