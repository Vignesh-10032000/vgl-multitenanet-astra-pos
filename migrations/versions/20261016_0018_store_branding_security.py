"""Persist store branding and revocable identity sessions.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Store normalized logos and invalidate all sessions after access changes."""
    op.add_column("companies", sa.Column("logo_data_uri", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    """Remove optional branding and session revocation state."""
    op.drop_column("users", "session_version")
    op.drop_column("companies", "logo_data_uri")
