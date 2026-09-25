"""Add Phase 8 purchasing, inventory depth, and queued reporting state.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from vglpos.migration_schema import BIGINT, audit_columns, create_index, id_column, tenant_column

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _create_existing_table_foreign_keys() -> None:
    foreign_keys = (
        (
            "fk_products_parent_product_id_products",
            "products",
            "products",
            ["parent_product_id"],
            ["id"],
        ),
        (
            "fk_products_preferred_supplier_id_suppliers",
            "products",
            "suppliers",
            ["preferred_supplier_id"],
            ["id"],
        ),
        (
            "fk_sale_items_supplier_id_at_sale_suppliers",
            "sale_items",
            "suppliers",
            ["supplier_id_at_sale"],
            ["id"],
        ),
        (
            "fk_purchases_purchase_order_id_purchase_orders",
            "purchases",
            "purchase_orders",
            ["purchase_order_id"],
            ["id"],
        ),
        (
            "fk_purchases_goods_receipt_id_goods_receipts",
            "purchases",
            "goods_receipts",
            ["goods_receipt_id"],
            ["id"],
        ),
        (
            "fk_purchase_items_batch_id_stock_batches",
            "purchase_items",
            "stock_batches",
            ["batch_id"],
            ["id"],
        ),
    )
    if _is_postgresql():
        for name, source, referent, local, remote in foreign_keys:
            op.create_foreign_key(name, source, referent, local, remote, ondelete="RESTRICT")
        return
    by_table: dict[str, list[tuple[str, str, list[str], list[str]]]] = {}
    for name, source, referent, local, remote in foreign_keys:
        by_table.setdefault(source, []).append((name, referent, local, remote))
    for table_name, definitions in by_table.items():
        with op.batch_alter_table(table_name) as batch_op:
            for name, referent, local, remote in definitions:
                batch_op.create_foreign_key(name, referent, local, remote, ondelete="RESTRICT")


def _drop_existing_table_foreign_keys_and_columns() -> None:
    definitions = {
        "purchase_items": (("fk_purchase_items_batch_id_stock_batches", "batch_id"),),
        "purchases": (
            ("fk_purchases_goods_receipt_id_goods_receipts", "goods_receipt_id"),
            ("fk_purchases_purchase_order_id_purchase_orders", "purchase_order_id"),
        ),
        "sale_items": (("fk_sale_items_supplier_id_at_sale_suppliers", "supplier_id_at_sale"),),
        "products": (
            ("fk_products_preferred_supplier_id_suppliers", "preferred_supplier_id"),
            ("fk_products_parent_product_id_products", "parent_product_id"),
        ),
    }
    if _is_postgresql():
        for table_name, items in definitions.items():
            for constraint, column in items:
                op.drop_constraint(constraint, table_name, type_="foreignkey")
                op.drop_column(table_name, column)
        return
    for table_name, items in definitions.items():
        with op.batch_alter_table(table_name) as batch_op:
            for constraint, _column in items:
                batch_op.drop_constraint(constraint, type_="foreignkey")
            for _constraint, column in items:
                batch_op.drop_column(column)


def upgrade() -> None:
    """Persist purchase matching, lot custody, counts, transfers, and report jobs."""
    op.add_column(
        "companies",
        sa.Column(
            "purchase_quantity_tolerance_percent",
            sa.Numeric(5, 2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "purchase_price_tolerance_percent",
            sa.Numeric(5, 2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
    )
    op.add_column(
        "companies",
        sa.Column("near_expiry_days", sa.Integer(), server_default=sa.text("30"), nullable=False),
    )
    op.add_column(
        "companies",
        sa.Column(
            "expired_stock_policy",
            sa.String(length=10),
            server_default=sa.text("'BLOCK'"),
            nullable=False,
        ),
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "outstanding_balance",
            sa.Numeric(14, 2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
    )
    for column in (
        sa.Column("parent_product_id", BIGINT, nullable=True),
        sa.Column("preferred_supplier_id", BIGINT, nullable=True),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("variant_size", sa.String(length=50), nullable=True),
        sa.Column("variant_colour", sa.String(length=50), nullable=True),
        sa.Column("variant_style", sa.String(length=50), nullable=True),
        sa.Column(
            "batch_tracking_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "safety_stock",
            sa.Numeric(12, 3),
            server_default=sa.text("0.000"),
            nullable=False,
        ),
        sa.Column("lead_time_days", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unit_weight_kg", sa.Numeric(12, 3), nullable=True),
    ):
        op.add_column("products", column)
    op.add_column(
        "sale_items",
        sa.Column(
            "cost_at_sale", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False
        ),
    )
    op.add_column("sale_items", sa.Column("supplier_id_at_sale", BIGINT, nullable=True))
    op.add_column("sale_items", sa.Column("hsn_code_at_sale", sa.String(length=10), nullable=True))
    op.add_column(
        "sale_items",
        sa.Column(
            "uqc_at_sale",
            sa.String(length=10),
            server_default=sa.text("'OTH'"),
            nullable=False,
        ),
    )
    op.add_column("sales", sa.Column("place_of_supply", sa.String(length=2), nullable=True))
    op.add_column("sales", sa.Column("customer_gstin_at_sale", sa.String(length=15), nullable=True))
    op.add_column("sales", sa.Column("customer_name_at_sale", sa.String(length=255), nullable=True))
    op.add_column(
        "credit_notes",
        sa.Column(
            "note_date",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
    )

    op.create_table(
        "purchase_orders",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id", BIGINT, sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "supplier_id",
            BIGINT,
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("order_number", sa.String(length=64), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *audit_columns(created_by_nullable=False),
    )
    create_index(
        "uq_purchase_orders_number",
        "purchase_orders",
        ["company_id", "order_number"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "purchase_order_items",
        id_column(),
        tenant_column(),
        sa.Column(
            "purchase_order_id",
            BIGINT,
            sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id", BIGINT, sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("ordered_quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        *audit_columns(created_by_nullable=False),
        sa.CheckConstraint("ordered_quantity > 0", name="ck_purchase_order_items_quantity"),
    )
    op.create_index("idx_purchase_order_items_order", "purchase_order_items", ["purchase_order_id"])

    op.create_table(
        "goods_receipts",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id", BIGINT, sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "supplier_id",
            BIGINT,
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "purchase_order_id",
            BIGINT,
            sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("grn_number", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'RECEIVED'"), nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        *audit_columns(created_by_nullable=False),
    )
    create_index(
        "uq_goods_receipts_number",
        "goods_receipts",
        ["company_id", "grn_number"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "goods_receipt_items",
        id_column(),
        tenant_column(),
        sa.Column(
            "goods_receipt_id",
            BIGINT,
            sa.ForeignKey("goods_receipts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "purchase_order_item_id",
            BIGINT,
            sa.ForeignKey("purchase_order_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_id", BIGINT, sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("batch_number", sa.String(length=100), nullable=True),
        sa.Column("mfg_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("received_quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        *audit_columns(created_by_nullable=False),
        sa.CheckConstraint("received_quantity > 0", name="ck_goods_receipt_items_quantity"),
    )
    op.create_index("idx_goods_receipt_items_receipt", "goods_receipt_items", ["goods_receipt_id"])

    op.add_column("purchases", sa.Column("purchase_order_id", BIGINT, nullable=True))
    op.add_column("purchases", sa.Column("goods_receipt_id", BIGINT, nullable=True))
    op.add_column("purchases", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column(
        "purchases",
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'POSTED'"), nullable=False
        ),
    )
    for name in (
        "taxable_amount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "landed_cost_amount",
        "amount_paid",
        "outstanding_amount",
    ):
        op.add_column(
            "purchases",
            sa.Column(name, sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        )
    op.add_column("purchase_items", sa.Column("batch_id", BIGINT, nullable=True))
    for name in (
        "taxable_amount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "landed_cost_amount",
        "unit_landed_cost",
    ):
        op.add_column(
            "purchase_items",
            sa.Column(name, sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
        )
    _create_existing_table_foreign_keys()
    create_index(
        "uq_purchases_supplier_invoice",
        "purchases",
        ["company_id", "supplier_id", "invoice_number"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "purchase_returns",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id", BIGINT, sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "supplier_id",
            BIGINT,
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "purchase_id",
            BIGINT,
            sa.ForeignKey("purchases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("debit_note_number", sa.String(length=64), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("cgst_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("sgst_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("igst_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("cess_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        *audit_columns(created_by_nullable=False),
    )
    create_index(
        "uq_purchase_returns_debit_note",
        "purchase_returns",
        ["company_id", "debit_note_number"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "purchase_return_items",
        id_column(),
        tenant_column(),
        sa.Column(
            "purchase_return_id",
            BIGINT,
            sa.ForeignKey("purchase_returns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "purchase_item_id",
            BIGINT,
            sa.ForeignKey("purchase_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_id", BIGINT, sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "batch_id",
            BIGINT,
            sa.ForeignKey("stock_batches.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        *audit_columns(created_by_nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_return_items_quantity"),
    )

    op.create_table(
        "supplier_ledger",
        id_column(),
        tenant_column(),
        sa.Column(
            "supplier_id",
            BIGINT,
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("txn_type", sa.String(length=30), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=False),
        sa.Column("reference_id", sa.String(length=100), nullable=False),
        sa.Column("debit_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("credit_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *audit_columns(created_by_nullable=False),
    )
    create_index(
        "idx_supplier_ledger_supplier_date",
        "supplier_ledger",
        ["company_id", "supplier_id", "txn_date", "id"],
    )

    op.create_table(
        "sale_item_batches",
        id_column(),
        tenant_column(),
        sa.Column(
            "sale_item_id",
            BIGINT,
            sa.ForeignKey("sale_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            BIGINT,
            sa.ForeignKey("stock_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        *audit_columns(created_by_nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_sale_item_batches_quantity"),
    )
    op.create_index("idx_sale_item_batches_item", "sale_item_batches", ["sale_item_id"])

    op.create_table(
        "credit_note_item_batches",
        id_column(),
        tenant_column(),
        sa.Column(
            "credit_note_item_id",
            BIGINT,
            sa.ForeignKey("credit_note_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sale_item_batch_id",
            BIGINT,
            sa.ForeignKey("sale_item_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            BIGINT,
            sa.ForeignKey("stock_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        *audit_columns(created_by_nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_credit_note_item_batches_quantity"),
    )
    op.create_index(
        "idx_credit_note_item_batches_item",
        "credit_note_item_batches",
        ["credit_note_item_id"],
    )

    op.create_table(
        "stock_audits",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id", BIGINT, sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("audit_number", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'DRAFT'"), nullable=False
        ),
        sa.Column("counted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        *audit_columns(created_by_nullable=False),
    )
    op.create_table(
        "stock_audit_items",
        id_column(),
        tenant_column(),
        sa.Column(
            "stock_audit_id",
            BIGINT,
            sa.ForeignKey("stock_audits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id", BIGINT, sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "batch_id",
            BIGINT,
            sa.ForeignKey("stock_batches.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("expected_quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("counted_quantity", sa.Numeric(12, 3), nullable=True),
        sa.Column("variance_quantity", sa.Numeric(12, 3), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        *audit_columns(created_by_nullable=False),
    )
    op.create_index("idx_stock_audit_items_audit", "stock_audit_items", ["stock_audit_id"])

    op.create_table(
        "stock_transfers",
        id_column(),
        tenant_column(),
        sa.Column(
            "source_branch_id",
            BIGINT,
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "destination_branch_id",
            BIGINT,
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("transfer_number", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'DRAFT'"), nullable=False
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *audit_columns(created_by_nullable=False),
    )
    create_index(
        "uq_stock_transfers_number",
        "stock_transfers",
        ["company_id", "transfer_number"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "stock_transfer_items",
        id_column(),
        tenant_column(),
        sa.Column(
            "stock_transfer_id",
            BIGINT,
            sa.ForeignKey("stock_transfers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id", BIGINT, sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "source_batch_id",
            BIGINT,
            sa.ForeignKey("stock_batches.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("received_quantity", sa.Numeric(12, 3), nullable=True),
        *audit_columns(created_by_nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_stock_transfer_items_quantity"),
    )
    op.create_index(
        "idx_stock_transfer_items_transfer", "stock_transfer_items", ["stock_transfer_id"]
    )

    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "report_jobs",
        id_column(),
        tenant_column(),
        sa.Column(
            "requested_by", BIGINT, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("report_name", sa.String(length=50), nullable=False),
        sa.Column("output_format", sa.String(length=20), nullable=False),
        sa.Column("parameters", json_type, nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'PENDING'"), nullable=False
        ),
        sa.Column("artifact_path", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *audit_columns(created_by_nullable=False),
    )
    op.create_index(
        "idx_report_jobs_company_status", "report_jobs", ["company_id", "status", "created_at"]
    )


def downgrade() -> None:
    """Remove Phase 8 business-depth state and restore the Phase 7 schema."""
    op.drop_table("report_jobs")
    op.drop_table("stock_transfer_items")
    op.drop_table("stock_transfers")
    op.drop_table("stock_audit_items")
    op.drop_table("stock_audits")
    op.drop_table("credit_note_item_batches")
    op.drop_table("sale_item_batches")
    op.drop_table("supplier_ledger")
    op.drop_table("purchase_return_items")
    op.drop_table("purchase_returns")
    op.drop_index("uq_purchases_supplier_invoice", table_name="purchases")
    _drop_existing_table_foreign_keys_and_columns()
    for name in (
        "unit_landed_cost",
        "landed_cost_amount",
        "cess_amount",
        "igst_amount",
        "sgst_amount",
        "cgst_amount",
        "taxable_amount",
    ):
        op.drop_column("purchase_items", name)
    for name in (
        "outstanding_amount",
        "amount_paid",
        "landed_cost_amount",
        "cess_amount",
        "igst_amount",
        "sgst_amount",
        "cgst_amount",
        "taxable_amount",
        "status",
        "due_date",
    ):
        op.drop_column("purchases", name)
    op.drop_table("goods_receipt_items")
    op.drop_table("goods_receipts")
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
    op.drop_column("credit_notes", "note_date")
    for name in ("customer_name_at_sale", "customer_gstin_at_sale", "place_of_supply"):
        op.drop_column("sales", name)
    op.drop_column("sale_items", "uqc_at_sale")
    op.drop_column("sale_items", "hsn_code_at_sale")
    op.drop_column("sale_items", "cost_at_sale")
    for name in (
        "unit_weight_kg",
        "lead_time_days",
        "safety_stock",
        "batch_tracking_enabled",
        "variant_style",
        "variant_colour",
        "variant_size",
        "brand",
    ):
        op.drop_column("products", name)
    op.drop_column("suppliers", "outstanding_balance")
    op.drop_column("companies", "expired_stock_policy")
    op.drop_column("companies", "near_expiry_days")
    op.drop_column("companies", "purchase_price_tolerance_percent")
    op.drop_column("companies", "purchase_quantity_tolerance_percent")
