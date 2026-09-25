"""Durable GST e-invoice, e-way bill, and invoice-template state."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import BIGINT, ActorTenantEntity


class EInvoice(ActorTenantEntity):
    """One durable IRP lifecycle record for a B2B sale."""

    __tablename__ = "e_invoices"
    __table_args__ = (
        Index(
            "uq_e_invoices_sale",
            "company_id",
            "sale_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_e_invoices_queue", "company_id", "status", "next_attempt_at", "id"),
    )

    sale_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[str] = mapped_column(
        String(10), default="1.1", server_default=text("'1.1'"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", server_default=text("'PENDING'"), nullable=False
    )
    request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    irn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ack_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ack_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_invoice: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_qr_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=5, server_default=text("5"), nullable=False
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EWayBill(ActorTenantEntity):
    """Durable e-way bill request sharing the e-invoice retry discipline."""

    __tablename__ = "e_way_bills"
    __table_args__ = (
        Index(
            "uq_e_way_bills_sale",
            "company_id",
            "sale_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_e_way_bills_queue", "company_id", "status", "next_attempt_at", "id"),
    )

    sale_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", server_default=text("'PENDING'"), nullable=False
    )
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    distance_km: Mapped[int] = mapped_column(Integer, nullable=False)
    transporter_id: Mapped[str | None] = mapped_column(String(15), nullable=True)
    transporter_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transport_mode: Mapped[str] = mapped_column(String(1), nullable=False)
    transport_document_number: Mapped[str | None] = mapped_column(String(15), nullable=True)
    transport_document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    vehicle_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vehicle_type: Mapped[str | None] = mapped_column(String(1), nullable=True)
    eway_bill_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    eway_bill_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=5, server_default=text("5"), nullable=False
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InvoiceTemplate(ActorTenantEntity):
    """Configurable Rule 46 field policy and printable declaration."""

    __tablename__ = "invoice_templates"
    __table_args__ = (
        Index(
            "uq_invoice_templates_code",
            "company_id",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    paper_size: Mapped[str] = mapped_column(
        String(10), default="A5", server_default=text("'A5'"), nullable=False
    )
    mandatory_fields: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    declaration_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
