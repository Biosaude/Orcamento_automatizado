"""Modelos de persistência PostgreSQL da plataforma Biosaúde."""

import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.persistence.base import Base


class CompanyORM(Base):
    """Empresa cadastrada na plataforma."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


class UserORM(Base):
    """Usuário vinculado a uma empresa."""

    __tablename__ = "users"

    __table_args__ = (
        Index("ix_users_identity_subject", "identity_subject"),
        UniqueConstraint(
            "company_id",
            "identity_subject",
            name="uq_users_company_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    identity_subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    company: Mapped["CompanyORM"] = relationship()


class HospitalORM(Base):
    """Hospital cadastrado e vinculado a uma empresa."""

    __tablename__ = "hospitals"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "id",
            name="uq_hospitals_company_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    quote_template: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="standard_vs_opme",
    )

    official_table_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    company: Mapped["CompanyORM"] = relationship()


class ProductORM(Base):
    """Produto hospitalar vinculado a uma empresa."""

    __tablename__ = "products"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "code",
            name="uq_products_company_code",
        ),
        UniqueConstraint(
            "company_id",
            "id",
            name="uq_products_company_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    manufacturer: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    company: Mapped["CompanyORM"] = relationship()


class QuoteRequestORM(Base):
    """Solicitação de orçamento vinculada a uma empresa e hospital."""

    __tablename__ = "quote_requests"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "id",
            name="uq_quote_requests_company_id",
        ),
        ForeignKeyConstraint(
            ["company_id", "hospital_id"],
            ["hospitals.company_id", "hospitals.id"],
            name="fk_quote_requests_company_hospital",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    hospital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    reference: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="received",
    )

    original_email_message_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    original_email_thread_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    company: Mapped["CompanyORM"] = relationship()

    hospital: Mapped["HospitalORM"] = relationship(
        viewonly=True,
    )


class QuoteItemORM(Base):
    """Material e quantidade solicitados em um orçamento."""

    __tablename__ = "quote_items"

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "request_id"],
            ["quote_requests.company_id", "quote_requests.id"],
            name="fk_quote_items_company_request",
        ),
        ForeignKeyConstraint(
            ["company_id", "product_id"],
            ["products.company_id", "products.id"],
            name="fk_quote_items_company_product",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_quote_items_quantity_positive",
        ),
        CheckConstraint(
            "unit_price >= 0",
            name="ck_quote_items_unit_price_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        nullable=False,
    )

    unit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )
