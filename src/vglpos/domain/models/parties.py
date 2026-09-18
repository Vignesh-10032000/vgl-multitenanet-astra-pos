"""Customer and supplier aggregate models."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import BIGINT, TenantEntity


class Customer(TenantEntity):
    """Tenant customer used for loyalty, credit, and B2B GST invoices."""

    __tablename__ = "customers"
    __table_args__ = (
        Index(
            "uq_customers_company_phone",
            "company_id",
            "phone",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_customers_company_name", "company_id", "name"),
    )

    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    state_code: Mapped[str] = mapped_column(
        String(2), default="33", server_default=text("'33'"), nullable=False
    )
    loyalty_points: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        default=Decimal("0.000"),
        server_default=text("0.000"),
        nullable=False,
    )
    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    total_orders: Mapped[int] = mapped_column(
        BIGINT, default=0, server_default=text("0"), nullable=False
    )
    credit_limit: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    outstanding_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class Supplier(TenantEntity):
    """Tenant supplier retained on purchase documents."""

    __tablename__ = "suppliers"
    __table_args__ = (
        Index(
            "uq_suppliers_company_code",
            "company_id",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms_days: Mapped[int] = mapped_column(
        default=30, server_default=text("30"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
