"""Inventory batch, ledger, and purchase aggregate models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import BIGINT, TenantEntity


class StockBatch(TenantEntity):
    """Branch stock lot used for expiry and valuation tracking."""

    __tablename__ = "stock_batches"
    __table_args__ = (
        Index(
            "uq_batches_product_number",
            "branch_id",
            "product_id",
            "batch_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_batches_expiry", "branch_id", "expiry_date"),
    )

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False)
    mfg_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_available: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class StockLedger(TenantEntity):
    """Append-only stock movement with its post-movement balance snapshot."""

    __tablename__ = "stock_ledger"
    __table_args__ = (Index("idx_stock_ledger_reference", "reference_type", "reference_id"),)

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("stock_batches.id", ondelete="RESTRICT"), nullable=True
    )
    txn_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


Index(
    "idx_stock_ledger_product_lookup",
    StockLedger.branch_id,
    StockLedger.product_id,
    StockLedger.created_at.desc(),
)


class Purchase(TenantEntity):
    """Supplier purchase aggregate root."""

    __tablename__ = "purchases"
    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class PurchaseItem(TenantEntity):
    """Product quantity and tax snapshot on a supplier purchase."""

    __tablename__ = "purchase_items"
    purchase_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


# Backward-compatible import name; both names reference the same mapped table.
StockLedgerEntry = StockLedger
