"""Company model (tenant root)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vglpos.extensions import Base

if TYPE_CHECKING:
    from vglpos.domain.models.branch import Branch
    from vglpos.domain.models.catalog import Product
    from vglpos.domain.models.register import Register
    from vglpos.domain.models.stock import StockLedgerEntry
    from vglpos.domain.models.tax_rate import TaxRate


class Company(Base):
    """Tenant root model for multi-company retail operations."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True, unique=True, index=True)

    # Address
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Contact
    contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Status & Timestamps
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    branches: Mapped[list[Branch]] = relationship(
        "Branch", back_populates="company", cascade="all, delete-orphan"
    )
    registers: Mapped[list[Register]] = relationship("Register", back_populates="company")
    products: Mapped[list[Product]] = relationship("Product", back_populates="company")
    tax_rates: Mapped[list[TaxRate]] = relationship("TaxRate", back_populates="company")
    stock_ledger_entries: Mapped[list[StockLedgerEntry]] = relationship(
        "StockLedgerEntry", back_populates="company"
    )
