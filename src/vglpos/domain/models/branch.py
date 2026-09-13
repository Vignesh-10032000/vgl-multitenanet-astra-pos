"""Branch model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vglpos.extensions import Base

if TYPE_CHECKING:
    from vglpos.domain.models.company import Company
    from vglpos.domain.models.register import Register
    from vglpos.domain.models.stock import StockLedgerEntry


class Branch(Base):
    """Store branch location belonging to a Company."""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Address
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Branch-specific GSTIN if applicable (distinct state registration)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)

    # Status & Timestamps
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    company: Mapped[Company] = relationship("Company", back_populates="branches")
    registers: Mapped[list[Register]] = relationship("Register", back_populates="branch", cascade="all, delete-orphan")
    stock_ledger_entries: Mapped[list[StockLedgerEntry]] = relationship("StockLedgerEntry", back_populates="branch")
