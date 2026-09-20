"""Add Phase 4 hot-path indexes and a cess-complete sales summary view.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from vglpos.migration_schema import create_index

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_BASE_SUMMARY_COLUMNS = """
    company_id,
    branch_id,
    business_date,
    COUNT(id) AS total_bills,
    SUM(gross_amount) AS total_gross,
    SUM(discount_amount) AS total_discount,
    SUM(taxable_amount) AS total_taxable,
    SUM(cgst_amount) AS total_cgst,
    SUM(sgst_amount) AS total_sgst,
    SUM(igst_amount) AS total_igst,
"""


def _summary_query(*, include_cess: bool) -> str:
    cess_column = "    SUM(cess_amount) AS total_cess,\n" if include_cess else ""
    return f"""
SELECT
{_BASE_SUMMARY_COLUMNS}{cess_column}    SUM(round_off) AS total_round_off,
    SUM(net_amount) AS total_net
FROM sales
WHERE sale_status = 'COMPLETED' AND deleted_at IS NULL
GROUP BY company_id, branch_id, business_date
"""


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _replace_summary_view(*, include_cess: bool) -> None:
    query = _summary_query(include_cess=include_cess)
    if _is_postgresql():
        op.execute("DROP MATERIALIZED VIEW mv_daily_sales_summary")
        op.execute(f"CREATE MATERIALIZED VIEW mv_daily_sales_summary AS {query}")
        create_index(
            "uq_mv_daily_sales",
            "mv_daily_sales_summary",
            ["branch_id", "business_date"],
            unique=True,
            large_table=True,
        )
        return
    op.execute("DROP VIEW mv_daily_sales_summary")
    op.execute(f"CREATE VIEW mv_daily_sales_summary AS {query}")


def _drop_hot_index(name: str, table_name: str) -> None:
    if _is_postgresql():
        with op.get_context().autocommit_block():
            op.drop_index(name, table_name=table_name, postgresql_concurrently=True)
        return
    op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    """Create compound hot-path indexes without blocking PostgreSQL writes."""
    live_rows = sa.text("deleted_at IS NULL")
    create_index(
        "idx_products_company_created",
        "products",
        ["company_id", "created_at", "id"],
        where=live_rows,
        large_table=True,
    )
    create_index(
        "idx_customers_company_created",
        "customers",
        ["company_id", "created_at", "id"],
        where=live_rows,
        large_table=True,
    )
    create_index(
        "idx_sales_company_branch_created",
        "sales",
        ["company_id", "branch_id", "created_at", "id"],
        where=live_rows,
        large_table=True,
    )
    create_index(
        "idx_sales_company_branch_status_date",
        "sales",
        ["company_id", "branch_id", "sale_status", "business_date"],
        where=live_rows,
        large_table=True,
    )
    _replace_summary_view(include_cess=True)


def downgrade() -> None:
    """Restore the original view and remove only Phase 4 indexes."""
    _replace_summary_view(include_cess=False)
    _drop_hot_index("idx_sales_company_branch_status_date", "sales")
    _drop_hot_index("idx_sales_company_branch_created", "sales")
    _drop_hot_index("idx_customers_company_created", "customers")
    _drop_hot_index("idx_products_company_created", "products")
