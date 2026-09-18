"""Create fiscal document and billing aggregates.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from vglpos.migration_schema import BIGINT, audit_columns, create_index, id_column, tenant_column

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create numbering, invoices, tender splits, and credit notes."""
    op.create_table(
        "document_series",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id",
            BIGINT,
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("doc_type", sa.String(50), nullable=False),
        sa.Column("prefix", sa.String(20), nullable=False),
        sa.Column("current_number", BIGINT, server_default=sa.text("0"), nullable=False),
        sa.Column("financial_year", sa.String(10), nullable=False),
        sa.Column("suffix", sa.String(20), nullable=True),
        *audit_columns(),
    )
    op.create_index(
        "uq_series_branch_type_fy",
        "document_series",
        ["branch_id", "doc_type", "financial_year"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "sales",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id",
            BIGINT,
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "terminal_id",
            BIGINT,
            sa.ForeignKey("terminals.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            BIGINT,
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "cashier_id",
            BIGINT,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # The shift FK is added by migration 0008 after shifts exists.
        sa.Column("shift_id", BIGINT, nullable=True),
        sa.Column("offline_uuid", sa.String(36), nullable=True),
        sa.Column("invoice_number", sa.String(64), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column(
            "sale_status", sa.String(50), server_default=sa.text("'COMPLETED'"), nullable=False
        ),
        sa.Column(
            "supply_type", sa.String(20), server_default=sa.text("'INTRASTATE'"), nullable=False
        ),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "discount_amount", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False
        ),
        sa.Column("taxable_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("cgst_amount", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("sgst_amount", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("igst_amount", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("cess_amount", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("round_off", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_due", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("payment_method", sa.String(50), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *audit_columns(),
        sa.CheckConstraint(
            "taxable_amount + cgst_amount + sgst_amount + igst_amount + "
            "cess_amount + round_off = net_amount",
            name="ck_sales_reconcile",
        ),
        sa.CheckConstraint(
            "(cgst_amount > 0 AND sgst_amount > 0 AND igst_amount = 0) OR "
            "(cgst_amount = 0 AND sgst_amount = 0 AND igst_amount >= 0) OR "
            "(cgst_amount = 0 AND sgst_amount = 0 AND igst_amount = 0)",
            name="ck_sales_tax_mode",
        ),
    )
    create_index(
        "uq_sales_company_invoice",
        "sales",
        ["company_id", "invoice_number"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
        large_table=True,
    )
    create_index(
        "uq_sales_company_offline_uuid",
        "sales",
        ["company_id", "offline_uuid"],
        unique=True,
        where=sa.text("deleted_at IS NULL AND offline_uuid IS NOT NULL"),
        large_table=True,
    )
    create_index(
        "idx_sales_branch_business_date",
        "sales",
        ["branch_id", "business_date"],
        large_table=True,
    )
    create_index(
        "idx_sales_customer",
        "sales",
        ["customer_id"],
        large_table=True,
    )

    op.create_table(
        "sale_items",
        id_column(),
        tenant_column(),
        sa.Column(
            "sale_id",
            BIGINT,
            sa.ForeignKey("sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            BIGINT,
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "discount_amount", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False
        ),
        sa.Column("taxable_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("cgst_rate", sa.Numeric(5, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("sgst_rate", sa.Numeric(5, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("igst_rate", sa.Numeric(5, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("cess_rate", sa.Numeric(5, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("cgst_amount", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("sgst_amount", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("igst_amount", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("cess_amount", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        *audit_columns(),
        sa.CheckConstraint("quantity > 0", name="ck_sale_items_qty"),
    )
    create_index("idx_sale_items_sale_id", "sale_items", ["sale_id"], large_table=True)
    create_index("idx_sale_items_product_id", "sale_items", ["product_id"], large_table=True)

    op.create_table(
        "sale_payments",
        id_column(),
        tenant_column(),
        sa.Column(
            "sale_id",
            BIGINT,
            sa.ForeignKey("sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payment_method", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reference_number", sa.String(100), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        *audit_columns(),
    )

    op.create_table(
        "credit_notes",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id",
            BIGINT,
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "original_sale_id",
            BIGINT,
            sa.ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("credit_note_number", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        *audit_columns(),
    )
    create_index(
        "uq_credit_notes_number",
        "credit_notes",
        ["company_id", "credit_note_number"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
        large_table=True,
    )

    op.create_table(
        "credit_note_items",
        id_column(),
        tenant_column(),
        sa.Column(
            "credit_note_id",
            BIGINT,
            sa.ForeignKey("credit_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "original_sale_item_id",
            BIGINT,
            sa.ForeignKey("sale_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        *audit_columns(),
    )


def downgrade() -> None:
    """Remove fiscal document tables."""
    op.drop_table("credit_note_items")
    op.drop_table("credit_notes")
    op.drop_table("sale_payments")
    op.drop_table("sale_items")
    op.drop_table("sales")
    op.drop_table("document_series")
