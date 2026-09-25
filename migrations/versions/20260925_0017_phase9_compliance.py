"""Add Phase 9 e-invoice, e-way bill, and Rule 46 compliance state.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from vglpos.migration_schema import BIGINT, audit_columns, create_index, id_column, tenant_column

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Persist provider-neutral compliance queues and configurable invoice controls."""
    company_columns = (
        sa.Column(
            "e_invoice_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "e_invoice_provider",
            sa.String(length=20),
            server_default=sa.text("'NIC'"),
            nullable=False,
        ),
        sa.Column(
            "e_invoice_reporting_window_days",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column(
            "e_invoice_retry_limit",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.Column(
            "composition_scheme_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "composition_declaration",
            sa.Text(),
            server_default=sa.text(
                "'Composition taxable person, not eligible to collect tax on supplies.'"
            ),
            nullable=False,
        ),
        sa.Column(
            "invoice_validation_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("gst_filing_locked_through", sa.Date(), nullable=True),
    )
    for column in company_columns:
        op.add_column("companies", column)
    op.add_column("customers", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("customers", sa.Column("postal_code", sa.String(length=10), nullable=True))

    op.create_table(
        "e_invoices",
        id_column(),
        tenant_column(),
        sa.Column(
            "sale_id", BIGINT, sa.ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column(
            "schema_version",
            sa.String(length=10),
            server_default=sa.text("'1.1'"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'PENDING'"), nullable=False
        ),
        sa.Column("request_json", sa.Text(), nullable=True),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("irn", sa.String(length=64), nullable=True),
        sa.Column("ack_number", sa.String(length=64), nullable=True),
        sa.Column("ack_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_invoice", sa.Text(), nullable=True),
        sa.Column("signed_qr_code", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(length=100), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        *audit_columns(created_by_nullable=False),
    )
    create_index(
        "uq_e_invoices_sale",
        "e_invoices",
        ["company_id", "sale_id"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_e_invoices_queue",
        "e_invoices",
        ["company_id", "status", "next_attempt_at", "id"],
    )

    op.create_table(
        "e_way_bills",
        id_column(),
        tenant_column(),
        sa.Column(
            "sale_id", BIGINT, sa.ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'PENDING'"), nullable=False
        ),
        sa.Column("request_json", sa.Text(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("distance_km", sa.Integer(), nullable=False),
        sa.Column("transporter_id", sa.String(length=15), nullable=True),
        sa.Column("transporter_name", sa.String(length=100), nullable=True),
        sa.Column("transport_mode", sa.String(length=1), nullable=False),
        sa.Column("transport_document_number", sa.String(length=15), nullable=True),
        sa.Column("transport_document_date", sa.Date(), nullable=True),
        sa.Column("vehicle_number", sa.String(length=20), nullable=True),
        sa.Column("vehicle_type", sa.String(length=1), nullable=True),
        sa.Column("eway_bill_number", sa.String(length=20), nullable=True),
        sa.Column("eway_bill_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        *audit_columns(created_by_nullable=False),
    )
    create_index(
        "uq_e_way_bills_sale",
        "e_way_bills",
        ["company_id", "sale_id"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_e_way_bills_queue",
        "e_way_bills",
        ["company_id", "status", "next_attempt_at", "id"],
    )

    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "invoice_templates",
        id_column(),
        tenant_column(),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "paper_size", sa.String(length=10), server_default=sa.text("'A5'"), nullable=False
        ),
        sa.Column("mandatory_fields", json_type, nullable=False),
        sa.Column("declaration_text", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(created_by_nullable=False),
    )
    create_index(
        "uq_invoice_templates_code",
        "invoice_templates",
        ["company_id", "code"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Remove Phase 9 compliance state and restore the Phase 8 schema."""
    op.drop_table("invoice_templates")
    op.drop_table("e_way_bills")
    op.drop_table("e_invoices")
    op.drop_column("customers", "postal_code")
    op.drop_column("customers", "city")
    for name in (
        "gst_filing_locked_through",
        "invoice_validation_enabled",
        "composition_declaration",
        "composition_scheme_enabled",
        "e_invoice_retry_limit",
        "e_invoice_reporting_window_days",
        "e_invoice_provider",
        "e_invoice_enabled",
    ):
        op.drop_column("companies", name)
