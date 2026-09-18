"""Create customer and supplier parties.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from vglpos.migration_schema import audit_columns, create_index, id_column, tenant_column

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create company-scoped customer and supplier records."""
    op.create_table(
        "customers",
        id_column(),
        tenant_column(),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("state_code", sa.String(2), server_default=sa.text("'33'"), nullable=False),
        sa.Column(
            "loyalty_points", sa.Numeric(12, 3), server_default=sa.text("0.000"), nullable=False
        ),
        sa.Column(
            "credit_limit", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False
        ),
        sa.Column(
            "outstanding_balance",
            sa.Numeric(14, 2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(),
    )
    create_index(
        "uq_customers_company_phone",
        "customers",
        ["company_id", "phone"],
        unique=True,
        where=sa.text("deleted_at IS NULL"),
        large_table=True,
    )
    create_index(
        "idx_customers_company_name",
        "customers",
        ["company_id", "name"],
        large_table=True,
    )

    op.create_table(
        "suppliers",
        id_column(),
        tenant_column(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("contact_person", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("pan", sa.String(10), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("payment_terms_days", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(),
    )
    op.create_index(
        "uq_suppliers_company_code",
        "suppliers",
        ["company_id", "code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Remove supplier and customer tables."""
    op.drop_table("suppliers")
    op.drop_table("customers")
