"""Add Phase 7 retail-operation state and enforce one open terminal shift.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from vglpos.migration_schema import BIGINT, audit_columns, id_column, tenant_column

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Persist drawer controls, held bills, loyalty movements, and quick keys."""
    op.drop_index("idx_shifts_open", table_name="shifts")
    op.create_index(
        "idx_shifts_open",
        "shifts",
        ["terminal_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN' AND deleted_at IS NULL"),
        sqlite_where=sa.text("status = 'OPEN' AND deleted_at IS NULL"),
    )

    op.add_column(
        "companies",
        sa.Column(
            "shift_variance_threshold",
            sa.Numeric(14, 2),
            server_default=sa.text("50.00"),
            nullable=False,
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "loyalty_earn_divisor",
            sa.Numeric(14, 2),
            server_default=sa.text("10.00"),
            nullable=False,
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "loyalty_redemption_value",
            sa.Numeric(14, 2),
            server_default=sa.text("0.25"),
            nullable=False,
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "loyalty_redemption_cap_percent",
            sa.Numeric(5, 2),
            server_default=sa.text("25.00"),
            nullable=False,
        ),
    )

    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.add_column(
        "shifts",
        sa.Column(
            "opening_denominations", json_type, server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column("shifts", sa.Column("closing_denominations", json_type, nullable=True))
    op.add_column(
        "shifts",
        sa.Column("variance_approved_by", BIGINT, nullable=True),
    )
    if _is_postgresql():
        op.create_foreign_key(
            "fk_shifts_variance_approved_by_users",
            "shifts",
            "users",
            ["variance_approved_by"],
            ["id"],
            ondelete="RESTRICT",
        )
    else:
        with op.batch_alter_table("shifts") as batch_op:
            batch_op.create_foreign_key(
                "fk_shifts_variance_approved_by_users",
                "users",
                ["variance_approved_by"],
                ["id"],
                ondelete="RESTRICT",
            )
    op.add_column("shifts", sa.Column("variance_reason", sa.Text(), nullable=True))
    op.add_column("sale_payments", sa.Column("loyalty_points", sa.Numeric(12, 3), nullable=True))
    op.add_column("products", sa.Column("image_path", sa.String(length=500), nullable=True))

    op.create_table(
        "held_bills",
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
            "shift_id",
            BIGINT,
            sa.ForeignKey("shifts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("cart_payload", json_type, nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'HELD'"), nullable=False),
        *audit_columns(created_by_nullable=False),
        sa.CheckConstraint("item_count > 0", name="ck_held_bills_item_count"),
        sa.CheckConstraint("net_amount >= 0", name="ck_held_bills_net_amount"),
    )
    op.create_index(
        "idx_held_bills_terminal_status",
        "held_bills",
        ["company_id", "terminal_id", "status", "created_at"],
    )

    op.create_table(
        "loyalty_ledger",
        id_column(),
        tenant_column(),
        sa.Column(
            "customer_id",
            BIGINT,
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "sale_id",
            BIGINT,
            sa.ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "credit_note_id",
            BIGINT,
            sa.ForeignKey("credit_notes.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("movement_type", sa.String(length=30), nullable=False),
        sa.Column("points", sa.Numeric(12, 3), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 3), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        *audit_columns(created_by_nullable=False),
        sa.CheckConstraint("points != 0", name="ck_loyalty_ledger_points_nonzero"),
    )
    op.create_index(
        "idx_loyalty_ledger_customer",
        "loyalty_ledger",
        ["company_id", "customer_id", "created_at", "id"],
    )

    op.create_table(
        "terminal_quick_keys",
        id_column(),
        tenant_column(),
        sa.Column(
            "terminal_id",
            BIGINT,
            sa.ForeignKey("terminals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            BIGINT,
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_number", sa.Integer(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(created_by_nullable=False),
        sa.CheckConstraint("key_number BETWEEN 1 AND 12", name="ck_terminal_quick_keys_number"),
    )
    op.create_index(
        "uq_terminal_quick_keys_number",
        "terminal_quick_keys",
        ["company_id", "terminal_id", "key_number"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_terminal_quick_keys_product",
        "terminal_quick_keys",
        ["company_id", "terminal_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Remove Phase 7 additions and restore the earlier non-unique shift index."""
    op.drop_table("terminal_quick_keys")
    op.drop_table("loyalty_ledger")
    op.drop_table("held_bills")
    op.drop_column("products", "image_path")
    op.drop_column("sale_payments", "loyalty_points")
    op.drop_column("shifts", "variance_reason")
    if _is_postgresql():
        op.drop_constraint("fk_shifts_variance_approved_by_users", "shifts", type_="foreignkey")
        op.drop_column("shifts", "variance_approved_by")
    else:
        with op.batch_alter_table("shifts") as batch_op:
            batch_op.drop_constraint("fk_shifts_variance_approved_by_users", type_="foreignkey")
            batch_op.drop_column("variance_approved_by")
    op.drop_column("shifts", "closing_denominations")
    op.drop_column("shifts", "opening_denominations")
    op.drop_column("companies", "loyalty_redemption_cap_percent")
    op.drop_column("companies", "loyalty_redemption_value")
    op.drop_column("companies", "loyalty_earn_divisor")
    op.drop_column("companies", "shift_variance_threshold")
    op.drop_index("idx_shifts_open", table_name="shifts")
    op.create_index(
        "idx_shifts_open",
        "shifts",
        ["terminal_id"],
        postgresql_where=sa.text("status = 'OPEN'"),
        sqlite_where=sa.text("status = 'OPEN'"),
    )
