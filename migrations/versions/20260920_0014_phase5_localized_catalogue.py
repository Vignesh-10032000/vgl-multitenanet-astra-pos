"""Add Phase 5 localized catalogue labels and weighed-item support.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add optional locale labels while retaining the canonical legacy name."""
    op.add_column("categories", sa.Column("name_en", sa.String(length=100), nullable=True))
    op.add_column("categories", sa.Column("name_ta", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("name_en", sa.String(length=255), nullable=True))
    op.add_column("products", sa.Column("name_ta", sa.String(length=255), nullable=True))
    op.add_column(
        "products",
        sa.Column(
            "is_weighed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.execute("UPDATE categories SET name_en = name WHERE name_en IS NULL")
    op.execute("UPDATE products SET name_en = name WHERE name_en IS NULL")


def downgrade() -> None:
    """Remove only the Phase 5 catalogue additions."""
    op.drop_column("products", "is_weighed")
    op.drop_column("products", "name_ta")
    op.drop_column("products", "name_en")
    op.drop_column("categories", "name_ta")
    op.drop_column("categories", "name_en")
