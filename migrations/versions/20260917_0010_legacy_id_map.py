"""Add legacy import identifier mappings.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from vglpos.migration_schema import BIGINT, audit_columns, id_column, tenant_column

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create audited provenance mappings for imported prototype rows."""
    op.create_table(
        "legacy_id_map",
        id_column(),
        tenant_column(),
        sa.Column("legacy_table", sa.String(64), nullable=False),
        sa.Column("legacy_id", sa.String(100), nullable=False),
        sa.Column("target_table", sa.String(64), nullable=False),
        sa.Column("target_id", BIGINT, nullable=False),
        *audit_columns(),
    )
    op.create_index(
        "uq_legacy_id_map_source",
        "legacy_id_map",
        ["company_id", "legacy_table", "legacy_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_legacy_id_map_target",
        "legacy_id_map",
        ["target_table", "target_id"],
    )


def downgrade() -> None:
    """Remove legacy provenance mappings without touching imported data."""
    op.drop_table("legacy_id_map")
