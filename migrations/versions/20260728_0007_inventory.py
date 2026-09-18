"""Create inventory batches, ledger, and purchasing tables.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from vglpos.migration_schema import BIGINT, audit_columns, create_index, id_column, tenant_column

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create batch-aware append-only stock and purchase aggregates."""
    op.create_table(
        "stock_batches",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id",
            BIGINT,
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            BIGINT,
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("batch_number", sa.String(100), nullable=False),
        sa.Column("mfg_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("cost_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("selling_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("quantity_received", sa.Numeric(12, 3), nullable=False),
        sa.Column("quantity_available", sa.Numeric(12, 3), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(),
    )
    create_index(
        "uq_batches_product_number",
        "stock_batches",
        ["branch_id", "product_id", "batch_number"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
        large_table=True,
    )
    create_index(
        "idx_batches_expiry",
        "stock_batches",
        ["branch_id", "expiry_date"],
        large_table=True,
    )

    op.create_table(
        "stock_ledger",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id",
            BIGINT,
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            BIGINT,
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            BIGINT,
            sa.ForeignKey("stock_batches.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("txn_type", sa.String(50), nullable=False),
        sa.Column("reference_id", sa.String(100), nullable=False),
        sa.Column("reference_type", sa.String(50), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *audit_columns(),
    )
    create_index(
        "idx_stock_ledger_product_lookup",
        "stock_ledger",
        ["branch_id", "product_id", sa.text("created_at DESC")],
        large_table=True,
    )
    create_index(
        "idx_stock_ledger_reference",
        "stock_ledger",
        ["reference_type", "reference_id"],
        large_table=True,
    )

    op.create_table(
        "purchases",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id",
            BIGINT,
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "supplier_id",
            BIGINT,
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("invoice_number", sa.String(100), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        *audit_columns(),
    )

    op.create_table(
        "purchase_items",
        id_column(),
        tenant_column(),
        sa.Column(
            "purchase_id",
            BIGINT,
            sa.ForeignKey("purchases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            BIGINT,
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("batch_number", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        *audit_columns(),
    )


def downgrade() -> None:
    """Remove purchasing and stock tables."""
    op.drop_table("purchase_items")
    op.drop_table("purchases")
    op.drop_table("stock_ledger")
    op.drop_table("stock_batches")
