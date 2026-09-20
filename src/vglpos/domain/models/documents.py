"""Fiscal document, sale, payment, and credit-note models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import BIGINT, TenantEntity


class DocumentSeries(TenantEntity):
    """Locked counter for consecutive fiscal document numbering."""

    __tablename__ = "document_series"
    __table_args__ = (
        Index(
            "uq_series_branch_type_fy",
            "branch_id",
            "doc_type",
            "financial_year",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    current_number: Mapped[int] = mapped_column(
        BIGINT, default=0, server_default=text("0"), nullable=False
    )
    financial_year: Mapped[str] = mapped_column(String(10), nullable=False)
    suffix: Mapped[str | None] = mapped_column(String(20), nullable=True)


class Sale(TenantEntity):
    """Immutable GST invoice aggregate root with reconciliation constraints."""

    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint(
            "ROUND(taxable_amount + cgst_amount + sgst_amount + igst_amount + "
            "cess_amount + round_off, 2) = net_amount",
            name="ck_sales_reconcile",
        ),
        CheckConstraint(
            "(cgst_amount > 0 AND sgst_amount > 0 AND igst_amount = 0) OR "
            "(cgst_amount = 0 AND sgst_amount = 0 AND igst_amount >= 0) OR "
            "(cgst_amount = 0 AND sgst_amount = 0 AND igst_amount = 0)",
            name="ck_sales_tax_mode",
        ),
        Index(
            "uq_sales_company_invoice",
            "company_id",
            "invoice_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_sales_company_offline_uuid",
            "company_id",
            "offline_uuid",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND offline_uuid IS NOT NULL"),
            sqlite_where=text("deleted_at IS NULL AND offline_uuid IS NOT NULL"),
        ),
        Index("idx_sales_branch_business_date", "branch_id", "business_date"),
        Index("idx_sales_customer", "customer_id"),
        Index(
            "idx_sales_company_branch_created",
            "company_id",
            "branch_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_sales_company_branch_status_date",
            "company_id",
            "branch_id",
            "sale_status",
            "business_date",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    terminal_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("terminals.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True
    )
    cashier_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    shift_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("shifts.id", ondelete="RESTRICT"), nullable=True
    )
    offline_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    sale_status: Mapped[str] = mapped_column(
        String(50), default="COMPLETED", server_default=text("'COMPLETED'"), nullable=False
    )
    supply_type: Mapped[str] = mapped_column(
        String(20), default="INTRASTATE", server_default=text("'INTRASTATE'"), nullable=False
    )
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
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
    round_off: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_due: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SaleItem(TenantEntity):
    """Tax snapshot and quantity for one immutable sale line."""

    __tablename__ = "sale_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_items_qty"),
        Index("idx_sale_items_sale_id", "sale_id"),
        Index("idx_sale_items_product_id", "product_id"),
    )

    sale_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cgst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    sgst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    igst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    cess_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
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
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class SalePayment(TenantEntity):
    """One tender component associated with a sale."""

    __tablename__ = "sale_payments"
    sale_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False
    )
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )


class CreditNote(TenantEntity):
    """Fiscal return document tied to the original sale."""

    __tablename__ = "credit_notes"
    __table_args__ = (
        Index(
            "uq_credit_notes_number",
            "company_id",
            "credit_note_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    original_sale_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False
    )
    credit_note_number: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class CreditNoteItem(TenantEntity):
    """Returned quantity and value from an original sale item."""

    __tablename__ = "credit_note_items"
    credit_note_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False
    )
    original_sale_item_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
