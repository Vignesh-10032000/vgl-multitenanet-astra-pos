"""Inventory batch, ledger, and purchase aggregate models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import BIGINT, ActorTenantEntity, TenantEntity


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
    __table_args__ = (
        Index(
            "uq_purchases_supplier_invoice",
            "company_id",
            "supplier_id",
            "invoice_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )
    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    purchase_order_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=True
    )
    goods_receipt_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("goods_receipts.id", ondelete="RESTRICT"), nullable=True
    )
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="POSTED", server_default=text("'POSTED'"), nullable=False
    )
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    cgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    sgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    cess_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    landed_cost_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    outstanding_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )


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
    batch_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("stock_batches.id", ondelete="RESTRICT"), nullable=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    cgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    sgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    cess_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    landed_cost_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    unit_landed_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class PurchaseOrder(ActorTenantEntity):
    """Approved supplier commitment used as the first leg of three-way matching."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        Index(
            "uq_purchase_orders_number",
            "company_id",
            "order_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    order_number: Mapped[str] = mapped_column(String(64), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="OPEN", server_default=text("'OPEN'"), nullable=False
    )
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PurchaseOrderItem(ActorTenantEntity):
    """Expected product, quantity, and price snapshot on a purchase order."""

    __tablename__ = "purchase_order_items"
    __table_args__ = (Index("idx_purchase_order_items_order", "purchase_order_id"),)

    purchase_order_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ordered_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class GoodsReceipt(ActorTenantEntity):
    """Physical receipt matched to an approved purchase order."""

    __tablename__ = "goods_receipts"
    __table_args__ = (
        Index(
            "uq_goods_receipts_number",
            "company_id",
            "grn_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    purchase_order_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False
    )
    grn_number: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="RECEIVED", server_default=text("'RECEIVED'"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class GoodsReceiptItem(ActorTenantEntity):
    """Accepted lot details for one ordered product."""

    __tablename__ = "goods_receipt_items"
    __table_args__ = (Index("idx_goods_receipt_items_receipt", "goods_receipt_id"),)

    goods_receipt_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_item_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("purchase_order_items.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mfg_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class PurchaseReturn(ActorTenantEntity):
    """GST debit note reducing stock and supplier liability."""

    __tablename__ = "purchase_returns"
    __table_args__ = (
        Index(
            "uq_purchase_returns_debit_note",
            "company_id",
            "debit_note_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    purchase_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=False
    )
    debit_note_number: Mapped[str] = mapped_column(String(64), nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cess_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class PurchaseReturnItem(ActorTenantEntity):
    """Returned quantity and tax snapshot tied to an original purchase line."""

    __tablename__ = "purchase_return_items"

    purchase_return_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("purchase_returns.id", ondelete="CASCADE"), nullable=False
    )
    purchase_item_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("purchase_items.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("stock_batches.id", ondelete="RESTRICT"), nullable=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class SupplierLedger(ActorTenantEntity):
    """Append-only supplier debit/credit movement with a running balance."""

    __tablename__ = "supplier_ledger"
    __table_args__ = (
        Index("idx_supplier_ledger_supplier_date", "company_id", "supplier_id", "txn_date", "id"),
    )

    supplier_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    txn_date: Mapped[date] = mapped_column(Date, nullable=False)
    txn_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class StockAudit(ActorTenantEntity):
    """Physical count workflow whose posting creates ledger-only adjustments."""

    __tablename__ = "stock_audits"

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    audit_number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="DRAFT", server_default=text("'DRAFT'"), nullable=False
    )
    counted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class StockAuditItem(ActorTenantEntity):
    """Expected, counted, and approved variance for one physical count line."""

    __tablename__ = "stock_audit_items"
    __table_args__ = (Index("idx_stock_audit_items_audit", "stock_audit_id"),)

    stock_audit_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("stock_audits.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("stock_batches.id", ondelete="RESTRICT"), nullable=True
    )
    expected_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    counted_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    variance_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class StockTransfer(ActorTenantEntity):
    """Inventory movement between branches with explicit in-transit custody."""

    __tablename__ = "stock_transfers"
    __table_args__ = (
        Index(
            "uq_stock_transfers_number",
            "company_id",
            "transfer_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    source_branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    destination_branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    transfer_number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="DRAFT", server_default=text("'DRAFT'"), nullable=False
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class StockTransferItem(ActorTenantEntity):
    """Requested and received quantity for one transfer product or lot."""

    __tablename__ = "stock_transfer_items"
    __table_args__ = (Index("idx_stock_transfer_items_transfer", "stock_transfer_id"),)

    stock_transfer_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("stock_transfers.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    source_batch_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("stock_batches.id", ondelete="RESTRICT"), nullable=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    received_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)


# Backward-compatible import name; both names reference the same mapped table.
StockLedgerEntry = StockLedger
