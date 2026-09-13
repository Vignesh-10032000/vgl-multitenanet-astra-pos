"""Tax Rate model (GST slabs and rate history)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vglpos.extensions import Base

if TYPE_CHECKING:
    from vglpos.domain.models.company import Company


class TaxRate(Base):
    """Company-scoped GST tax rate configuration."""

    __tablename__ = "tax_rates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Zero Float Rule: Tax rates are Numeric(5, 2) e.g. 2.50, 9.00, 18.00
    cgst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    sgst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    igst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )

    hsn_code_pattern: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Effective dates for rate history
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

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
    company: Mapped[Company] = relationship("Company", back_populates="tax_rates")
