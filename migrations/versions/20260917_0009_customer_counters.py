"""Add denormalized customer checkout counters.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from vglpos.migration_schema import BIGINT

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add counters maintained atomically by checkout and return services."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "idx_products_name_trgm",
        "products",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "idx_products_sku_trgm",
        "products",
        ["sku"],
        postgresql_using="gin",
        postgresql_ops={"sku": "gin_trgm_ops"},
    )
    op.add_column(
        "customers",
        sa.Column("total_spent", sa.Numeric(14, 2), server_default=sa.text("0.00"), nullable=False),
    )
    op.add_column(
        "customers",
        sa.Column("total_orders", BIGINT, server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    """Remove customer counters without affecting fiscal documents."""
    op.drop_column("customers", "total_orders")
    op.drop_column("customers", "total_spent")
    op.drop_index("idx_products_sku_trgm", table_name="products")
    op.drop_index("idx_products_name_trgm", table_name="products")
