"""Create stock_ledger table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

movement_enum = sa.Enum("purchase", "sale", "adjustment", "transfer", name="stock_movement_type")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        movement_enum.create(bind, checkfirst=True)

    op.create_table(
        "stock_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("movement_type", movement_enum, nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("reference_doc_id", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_stock_ledger_company_id_companies"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name=op.f("fk_stock_ledger_branch_id_branches"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["product_catalog.id"], name=op.f("fk_stock_ledger_product_id_product_catalog"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_ledger")),
    )
    op.create_index(op.f("ix_stock_ledger_company_id"), "stock_ledger", ["company_id"], unique=False)
    op.create_index(op.f("ix_stock_ledger_branch_id"), "stock_ledger", ["branch_id"], unique=False)
    op.create_index(op.f("ix_stock_ledger_product_id"), "stock_ledger", ["product_id"], unique=False)
    op.create_index(op.f("ix_stock_ledger_movement_type"), "stock_ledger", ["movement_type"], unique=False)
    op.create_index(op.f("ix_stock_ledger_reference_doc_id"), "stock_ledger", ["reference_doc_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_ledger_reference_doc_id"), table_name="stock_ledger")
    op.drop_index(op.f("ix_stock_ledger_movement_type"), table_name="stock_ledger")
    op.drop_index(op.f("ix_stock_ledger_product_id"), table_name="stock_ledger")
    op.drop_index(op.f("ix_stock_ledger_branch_id"), table_name="stock_ledger")
    op.drop_index(op.f("ix_stock_ledger_company_id"), table_name="stock_ledger")
    op.drop_table("stock_ledger")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        movement_enum.drop(bind, checkfirst=True)
