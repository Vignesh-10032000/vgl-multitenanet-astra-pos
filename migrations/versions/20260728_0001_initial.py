"""Initial empty revision.

Baseline anchor so ``alembic upgrade head`` and ``alembic downgrade base``
work before the first real schema migration exists.

Revision ID: 0001
Revises:
Create Date: 2026-07-28
"""

from __future__ import annotations

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No schema yet: this revision exists only to anchor the migration chain."""


def downgrade() -> None:
    """Nothing was created, so nothing is dropped."""
