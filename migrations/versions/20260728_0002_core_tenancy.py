"""Create companies, branches, and terminals.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from vglpos.migration_schema import BIGINT, audit_columns, id_column, tenant_column

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the tenant root and physical store hierarchy."""
    op.create_table(
        "companies",
        id_column(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("pan", sa.String(10), nullable=True),
        sa.Column("cin", sa.String(21), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'INR'"), nullable=False),
        sa.Column("address_line1", sa.String(255), nullable=False),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("postal_code", sa.String(10), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("contact_phone", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(with_user_fks=False),
    )
    op.create_index(
        "uq_companies_gstin",
        "companies",
        ["gstin"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND gstin IS NOT NULL"),
        sqlite_where=sa.text("deleted_at IS NULL AND gstin IS NOT NULL"),
    )
    op.create_index(
        "idx_companies_active",
        "companies",
        ["is_active"],
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "branches",
        id_column(),
        tenant_column(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=False),
        sa.Column("address_line1", sa.String(255), nullable=False),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("postal_code", sa.String(10), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("is_head_office", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *audit_columns(with_user_fks=False),
    )
    op.create_index(
        "uq_branches_company_code",
        "branches",
        ["company_id", "code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_branches_company_id", "branches", ["company_id"])

    op.create_table(
        "terminals",
        id_column(),
        tenant_column(),
        sa.Column(
            "branch_id",
            BIGINT,
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "terminal_type", sa.String(50), server_default=sa.text("'COUNTER'"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *audit_columns(with_user_fks=False),
    )
    op.create_index(
        "uq_terminals_branch_code",
        "terminals",
        ["branch_id", "code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_terminals_branch_id", "terminals", ["branch_id"])
    op.create_index("idx_terminals_company_id", "terminals", ["company_id"])


def downgrade() -> None:
    """Remove the tenant hierarchy in reverse dependency order."""
    op.drop_table("terminals")
    op.drop_table("branches")
    op.drop_table("companies")
