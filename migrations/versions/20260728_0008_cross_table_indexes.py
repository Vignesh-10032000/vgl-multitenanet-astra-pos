"""Add cross-table reporting indexes and constraints.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_stock_ledger_company_product_created",
        "stock_ledger",
        ["company_id", "product_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_stock_ledger_company_branch_product",
        "stock_ledger",
        ["company_id", "branch_id", "product_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_catalog_company_active_name",
        "product_catalog",
        ["company_id", "is_active", "name"],
        unique=False,
    )
    op.create_index(
        "ix_tax_rates_company_active_effective",
        "tax_rates",
        ["company_id", "is_active", "effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_registers_company_branch_code",
        "registers",
        ["company_id", "branch_id", "code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_registers_company_branch_code", table_name="registers")
    op.drop_index("ix_tax_rates_company_active_effective", table_name="tax_rates")
    op.drop_index("ix_product_catalog_company_active_name", table_name="product_catalog")
    op.drop_index("ix_stock_ledger_company_branch_product", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_company_product_created", table_name="stock_ledger")
