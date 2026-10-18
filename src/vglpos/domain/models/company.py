"""Company tenant-root model."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import AuditMixin, SurrogateKeyMixin
from vglpos.extensions import Base


class Company(AuditMixin, SurrogateKeyMixin, Base):
    """Legal entity that owns all tenant-scoped records."""

    __tablename__ = "companies"
    __table_args__ = (
        Index(
            "uq_companies_login_code",
            "login_code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND login_code IS NOT NULL"),
            sqlite_where=text("deleted_at IS NULL AND login_code IS NOT NULL"),
        ),
        Index(
            "uq_companies_gstin",
            "gstin",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND gstin IS NOT NULL"),
            sqlite_where=text("deleted_at IS NULL AND gstin IS NOT NULL"),
        ),
        Index(
            "idx_companies_active",
            "is_active",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    logo_data_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    login_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cin: Mapped[str | None] = mapped_column(String(21), nullable=True)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="INR", server_default=text("'INR'"), nullable=False
    )
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    shift_variance_threshold: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("50.00"), server_default=text("50.00"), nullable=False
    )
    loyalty_earn_divisor: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("10.00"), server_default=text("10.00"), nullable=False
    )
    loyalty_redemption_value: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.25"), server_default=text("0.25"), nullable=False
    )
    loyalty_redemption_cap_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("25.00"), server_default=text("25.00"), nullable=False
    )
    purchase_quantity_tolerance_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    purchase_price_tolerance_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    near_expiry_days: Mapped[int] = mapped_column(
        Integer, default=30, server_default=text("30"), nullable=False
    )
    expired_stock_policy: Mapped[str] = mapped_column(
        String(10), default="BLOCK", server_default=text("'BLOCK'"), nullable=False
    )
    e_invoice_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    e_invoice_provider: Mapped[str] = mapped_column(
        String(20), default="NIC", server_default=text("'NIC'"), nullable=False
    )
    e_invoice_reporting_window_days: Mapped[int] = mapped_column(
        Integer, default=30, server_default=text("30"), nullable=False
    )
    e_invoice_retry_limit: Mapped[int] = mapped_column(
        Integer, default=5, server_default=text("5"), nullable=False
    )
    composition_scheme_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    composition_declaration: Mapped[str] = mapped_column(
        Text,
        default="Composition taxable person, not eligible to collect tax on supplies.",
        server_default=text(
            "'Composition taxable person, not eligible to collect tax on supplies.'"
        ),
        nullable=False,
    )
    invoice_validation_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    gst_filing_locked_through: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
