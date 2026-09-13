"""Create branches table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("state_code", sa.String(length=2), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("gstin", sa.String(length=15), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_branches_company_id_companies"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_branches")),
    )
    op.create_index(op.f("ix_branches_company_id"), "branches", ["company_id"], unique=False)
    op.create_index(op.f("ix_branches_gstin"), "branches", ["gstin"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_branches_gstin"), table_name="branches")
    op.drop_index(op.f("ix_branches_company_id"), table_name="branches")
    op.drop_table("branches")
