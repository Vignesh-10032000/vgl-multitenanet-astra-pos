"""Create companies table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("state_code", sa.String(length=2), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("contact_name", sa.String(length=100), nullable=True),
        sa.Column("contact_phone", sa.String(length=20), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    op.create_index(op.f("ix_companies_gstin"), "companies", ["gstin"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_companies_gstin"), table_name="companies")
    op.drop_table("companies")
