"""GST catalogue, product, barcode, and price-history models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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

from vglpos.domain.models.base import BIGINT, GlobalEntity, TenantEntity


class TaxRate(TenantEntity):
    """Dated GST rate record retained for historical invoice reproduction."""

    __tablename__ = "tax_rates"
    __table_args__ = (
        CheckConstraint(
            "cgst_rate + sgst_rate = rate OR igst_rate = rate",
            name="ck_tax_rates_components",
        ),
        Index(
            "uq_tax_rates_company_name",
            "company_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cgst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    sgst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    igst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cess_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class HsnCode(GlobalEntity):
    """Global Harmonised System code with an optional default GST rate."""

    __tablename__ = "hsn_codes"
    __table_args__ = (
        Index(
            "uq_hsn_codes_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    default_tax_rate_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("tax_rates.id", ondelete="RESTRICT"), nullable=True
    )


class Category(TenantEntity):
    """Tenant product hierarchy node."""

    __tablename__ = "categories"
    __table_args__ = (
        Index(
            "uq_categories_company_code",
            "company_id",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class Product(TenantEntity):
    """Sellable catalogue item with authoritative stock and price fields."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "cost_price >= 0 AND selling_price >= 0 AND mrp >= selling_price",
            name="ck_products_prices",
        ),
        Index(
            "uq_products_company_sku",
            "company_id",
            "sku",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_products_company_category", "company_id", "category_id"),
        Index(
            "idx_products_company_created",
            "company_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_products_barcode",
            "company_id",
            "barcode",
            postgresql_where=text("barcode IS NOT NULL"),
            sqlite_where=text("barcode IS NOT NULL"),
        ),
        Index(
            "idx_products_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "idx_products_sku_trgm",
            "sku",
            postgresql_using="gin",
            postgresql_ops={"sku": "gin_trgm_ops"},
        ),
    )

    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )
    hsn_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("hsn_codes.id", ondelete="RESTRICT"), nullable=True
    )
    tax_rate_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("tax_rates.id", ondelete="RESTRICT"), nullable=False
    )
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uom: Mapped[str] = mapped_column(
        String(20), default="UNIT", server_default=text("'UNIT'"), nullable=False
    )
    cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    mrp: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_tax_inclusive: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    is_inventory_tracked: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    low_stock_threshold: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        default=Decimal("5.000"),
        server_default=text("5.000"),
        nullable=False,
    )
    on_hand: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        default=Decimal("0.000"),
        server_default=text("0.000"),
        nullable=False,
    )
    reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        default=Decimal("0.000"),
        server_default=text("0.000"),
        nullable=False,
    )
    allow_negative_stock: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class ProductBarcode(TenantEntity):
    """Additional scanner code belonging to one product."""

    __tablename__ = "product_barcodes"
    __table_args__ = (
        Index(
            "uq_product_barcodes_code",
            "company_id",
            "barcode",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_product_barcodes_product", "product_id"),
    )

    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    barcode: Mapped[str] = mapped_column(String(64), nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


class ProductPriceHistory(TenantEntity):
    """Append-only record of catalogue selling-price changes."""

    __tablename__ = "product_price_history"

    product_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    old_selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    new_selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    old_mrp: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    new_mrp: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    changed_by: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
