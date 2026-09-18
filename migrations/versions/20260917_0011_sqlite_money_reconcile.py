"""Compare invoice reconciliation at the persisted money precision.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_EXACT_EXPRESSION = (
    "taxable_amount + cgst_amount + sgst_amount + igst_amount + "
    "cess_amount + round_off = net_amount"
)
_MONEY_PRECISION_EXPRESSION = (
    "ROUND(taxable_amount + cgst_amount + sgst_amount + igst_amount + "
    "cess_amount + round_off, 2) = net_amount"
)
_SUMMARY_QUERY = """
SELECT
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
    SUM(round_off) AS total_round_off,
    SUM(net_amount) AS total_net
FROM sales
WHERE sale_status = 'COMPLETED' AND deleted_at IS NULL
GROUP BY company_id, branch_id, business_date
"""


def _replace_reconciliation_constraint(expression: str) -> None:
    """Use SQLite's table-copy path while retaining direct PostgreSQL DDL."""
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP VIEW mv_daily_sales_summary")
        with op.batch_alter_table("sales") as batch_op:
            batch_op.drop_constraint("ck_sales_reconcile", type_="check")
            batch_op.create_check_constraint("ck_sales_reconcile", expression)
        op.execute(f"CREATE VIEW mv_daily_sales_summary AS {_SUMMARY_QUERY}")
        return
    op.drop_constraint("ck_sales_reconcile", "sales", type_="check")
    op.create_check_constraint("ck_sales_reconcile", "sales", expression)


def upgrade() -> None:
    """Prevent SQLite binary numerics from rejecting exact two-paise values."""
    _replace_reconciliation_constraint(_MONEY_PRECISION_EXPRESSION)


def downgrade() -> None:
    """Restore direct equality for deployments that require the earlier DDL."""
    _replace_reconciliation_constraint(_EXACT_EXPRESSION)
