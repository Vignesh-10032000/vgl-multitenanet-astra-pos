"""Create GST reference and product catalogue tables.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from vglpos.migration_schema import BIGINT, audit_columns, create_index, id_column, tenant_column

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create dated tax rates, HSN codes, categories, and products."""
    op.create_table(
        "tax_rates",
        id_column(),
        tenant_column(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("cgst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("sgst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("igst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("cess_rate", sa.Numeric(5, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(),
        sa.CheckConstraint(
            "cgst_rate + sgst_rate = rate OR igst_rate = rate",
            name="ck_tax_rates_components",
        ),
    )
    op.create_index(
        "uq_tax_rates_company_name",
        "tax_rates",
        ["company_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "hsn_codes",
        id_column(),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column(
            "default_tax_rate_id",
            BIGINT,
            sa.ForeignKey("tax_rates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        *audit_columns(),
    )
    op.create_index(
        "uq_hsn_codes_code",
        "hsn_codes",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "categories",
        id_column(),
        tenant_column(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column(
            "parent_id",
            BIGINT,
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(),
    )
    op.create_index(
        "uq_categories_company_code",
        "categories",
        ["company_id", "code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "products",
        id_column(),
        tenant_column(),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "category_id",
            BIGINT,
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "hsn_id",
            BIGINT,
            sa.ForeignKey("hsn_codes.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "tax_rate_id",
            BIGINT,
            sa.ForeignKey("tax_rates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("barcode", sa.String(64), nullable=True),
        sa.Column("uom", sa.String(20), server_default=sa.text("'UNIT'"), nullable=False),
        sa.Column("cost_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("selling_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("mrp", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "is_tax_inclusive", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_inventory_tracked", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "low_stock_threshold",
            sa.Numeric(12, 3),
            server_default=sa.text("5.000"),
            nullable=False,
        ),
        sa.Column("on_hand", sa.Numeric(12, 3), server_default=sa.text("0.000"), nullable=False),
        sa.Column(
            "reserved_quantity", sa.Numeric(12, 3), server_default=sa.text("0.000"), nullable=False
        ),
        sa.Column(
            "allow_negative_stock", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(),
        sa.CheckConstraint(
            "cost_price >= 0 AND selling_price >= 0 AND mrp >= selling_price",
            name="ck_products_prices",
        ),
    )
    create_index(
        "uq_products_company_sku",
        "products",
        ["company_id", "sku"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
        large_table=True,
    )
    create_index(
        "idx_products_company_category",
        "products",
        ["company_id", "category_id"],
        large_table=True,
    )
    create_index(
        "idx_products_barcode",
        "products",
        ["company_id", "barcode"],
        where=sa.text("barcode IS NOT NULL"),
        large_table=True,
    )

    op.create_table(
        "product_barcodes",
        id_column(),
        tenant_column(),
        sa.Column(
            "product_id",
            BIGINT,
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("barcode", sa.String(64), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *audit_columns(),
    )
    create_index(
        "uq_product_barcodes_code",
        "product_barcodes",
        ["company_id", "barcode"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
        large_table=True,
    )
    create_index(
        "idx_product_barcodes_product",
        "product_barcodes",
        ["product_id"],
        large_table=True,
    )

    op.create_table(
        "product_price_history",
        id_column(),
        tenant_column(),
        sa.Column(
            "product_id",
            BIGINT,
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("old_selling_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("new_selling_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("old_mrp", sa.Numeric(14, 2), nullable=False),
        sa.Column("new_mrp", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "changed_by",
            BIGINT,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *audit_columns(),
    )


def downgrade() -> None:
    """Remove the catalogue in reverse dependency order."""
    op.drop_table("product_price_history")
    op.drop_table("product_barcodes")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_table("hsn_codes")
    op.drop_table("tax_rates")
