"""Create shifts, cash movements, audit partitions, and sales summary view.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from vglpos.migration_schema import BIGINT, audit_columns, create_index, id_column, tenant_column

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

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


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Create operational cash control and immutable audit structures."""
    op.create_table(
        "shifts",
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
            "cashier_id",
            BIGINT,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opening_cash", sa.Numeric(14, 2), nullable=False),
        sa.Column("closing_cash_expected", sa.Numeric(14, 2), nullable=True),
        sa.Column("closing_cash_counted", sa.Numeric(14, 2), nullable=True),
        sa.Column("cash_difference", sa.Numeric(14, 2), nullable=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *audit_columns(),
    )
    op.create_index(
        "idx_shifts_open",
        "shifts",
        ["terminal_id"],
        postgresql_where=sa.text("status = 'OPEN'"),
        sqlite_where=sa.text("status = 'OPEN'"),
    )

    op.create_table(
        "cash_movements",
        id_column(),
        tenant_column(),
        sa.Column(
            "shift_id",
            BIGINT,
            sa.ForeignKey("shifts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("movement_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        *audit_columns(created_by_nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", BIGINT, sa.Identity(always=True), nullable=False),
        tenant_column(),
        sa.Column("user_id", BIGINT, nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("old_values", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True),
        sa.Column("new_values", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_by",
            BIGINT,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_by",
            BIGINT,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "deleted_by",
            BIGINT,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("id", "created_at", name="pk_audit_log"),
        postgresql_partition_by="RANGE (created_at)",
    )
    if _is_postgresql():
        op.execute(
            "CREATE TABLE audit_log_y2026m07 PARTITION OF audit_log "
            "FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00')"
        )
        op.execute(
            "CREATE TABLE audit_log_y2026m08 PARTITION OF audit_log "
            "FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00')"
        )
        op.execute(
            "CREATE TABLE audit_log_y2026m09 PARTITION OF audit_log "
            "FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00')"
        )
        op.execute("CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT")

    if _is_postgresql():
        op.create_foreign_key(
            "fk_sales_shift_id_shifts",
            "sales",
            "shifts",
            ["shift_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.execute(f"CREATE MATERIALIZED VIEW mv_daily_sales_summary AS {_SUMMARY_QUERY}")
        create_index(
            "uq_mv_daily_sales",
            "mv_daily_sales_summary",
            ["branch_id", "business_date"],
            unique=True,
            large_table=True,
        )
    else:
        with op.batch_alter_table("sales") as batch_op:
            batch_op.create_foreign_key(
                "fk_sales_shift_id_shifts",
                "shifts",
                ["shift_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        op.execute(f"CREATE VIEW mv_daily_sales_summary AS {_SUMMARY_QUERY}")


def downgrade() -> None:
    """Remove views, audit data, and shift structures in dependency order."""
    if _is_postgresql():
        op.execute("DROP MATERIALIZED VIEW mv_daily_sales_summary")
        op.drop_constraint("fk_sales_shift_id_shifts", "sales", type_="foreignkey")
    else:
        op.execute("DROP VIEW mv_daily_sales_summary")
        with op.batch_alter_table("sales") as batch_op:
            batch_op.drop_constraint("fk_sales_shift_id_shifts", type_="foreignkey")
    op.drop_table("audit_log")
    op.drop_table("cash_movements")
    op.drop_table("shifts")
