"""Stock Ledger model (Append-only inventory movement log)."""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vglpos.extensions import Base

if TYPE_CHECKING:
    from vglpos.domain.models.branch import Branch
    from vglpos.domain.models.catalog import Product
    from vglpos.domain.models.company import Company


class StockMovementType(str, enum.Enum):
    """Enumeration of physical inventory movement types."""

    PURCHASE = "purchase"
    SALE = "sale"
    ADJUSTMENT = "adjustment"
    TRANSFER = "transfer"


class StockLedgerEntry(Base):
    """Append-only stock movement entry.

    Rule: Never updated after insert. No updated_at or is_edited fields.
    """

    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product_catalog.id", ondelete="RESTRICT"), nullable=False, index=True)

    movement_type: Mapped[StockMovementType] = mapped_column(
        Enum(
            StockMovementType,
            name="stock_movement_type",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )

    # Zero Float Rule: Quantities are Decimal with 3 decimal places (Numeric 12, 3)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    reference_doc_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Movement timestamp (append-only, no updated_at)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    company: Mapped[Company] = relationship("Company", back_populates="stock_ledger_entries")
    branch: Mapped[Branch] = relationship("Branch", back_populates="stock_ledger_entries")
    product: Mapped[Product] = relationship("Product", back_populates="stock_ledger_entries")
