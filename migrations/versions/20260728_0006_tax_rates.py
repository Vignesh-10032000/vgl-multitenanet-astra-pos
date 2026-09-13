"""Create tax_rates table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tax_rates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "cgst_rate",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "sgst_rate",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "igst_rate",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column("hsn_code_pattern", sa.String(length=20), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_tax_rates_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_rates")),
    )
    op.create_index(op.f("ix_tax_rates_company_id"), "tax_rates", ["company_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tax_rates_company_id"), table_name="tax_rates")
    op.drop_table("tax_rates")
