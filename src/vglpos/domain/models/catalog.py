"""Product Catalog model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vglpos.extensions import Base

if TYPE_CHECKING:
    from vglpos.domain.models.company import Company
    from vglpos.domain.models.stock import StockLedgerEntry


class Product(Base):
    """Product catalog item belonging to a Company."""

    __tablename__ = "product_catalog"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    unit_of_measure: Mapped[str] = mapped_column(
        String(20), default="PCS", server_default=text("'PCS'"), nullable=False
    )

    # Zero Float Rule: Money columns are Numeric(12, 2)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    mrp: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Statutory GST HSN code
    hsn_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)

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
    company: Mapped[Company] = relationship("Company", back_populates="products")
    stock_ledger_entries: Mapped[list[StockLedgerEntry]] = relationship(
        "StockLedgerEntry", back_populates="product"
    )
