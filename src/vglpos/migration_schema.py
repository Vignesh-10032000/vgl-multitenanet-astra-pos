"""Frozen column factories shared only by the Phase 1B migration series."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import ColumnElement, TextClause

BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def create_index(
    name: str,
    table_name: str,
    columns: Sequence[str | TextClause | ColumnElement[Any]],
    *,
    unique: bool = False,
    where: TextClause | None = None,
    large_table: bool = False,
) -> None:
    """Create an index, avoiding PostgreSQL write locks on large tables."""
    dialect_name = op.get_bind().dialect.name
    dialect_options: dict[str, Any] = {}
    if where is not None:
        dialect_options["postgresql_where"] = where
        dialect_options["sqlite_where"] = where

    if dialect_name == "postgresql" and large_table:
        dialect_options["postgresql_concurrently"] = True
        with op.get_context().autocommit_block():
            op.create_index(
                name,
                table_name,
                columns,
                unique=unique,
                **dialect_options,
            )
        return

    op.create_index(
        name,
        table_name,
        columns,
        unique=unique,
        **dialect_options,
    )


def id_column() -> sa.Column[int]:
    """Return the required PostgreSQL BIGINT identity primary key."""
    return sa.Column("id", BIGINT, sa.Identity(always=True), primary_key=True)


def tenant_column() -> sa.Column[int]:
    """Return the mandatory tenant boundary column."""
    return sa.Column(
        "company_id",
        BIGINT,
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )


def audit_columns(
    *, with_user_fks: bool = True, created_by_nullable: bool = True
) -> list[sa.Column[Any]]:
    """Return the complete audit/soft-delete/row-version column set."""

    def user_column(name: str, *, nullable: bool = True) -> sa.Column[Any]:
        if with_user_fks:
            return sa.Column(
                name,
                BIGINT,
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=nullable,
            )
        return sa.Column(name, BIGINT, nullable=nullable)

    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        user_column("created_by", nullable=created_by_nullable),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        user_column("updated_by"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        user_column("deleted_by"),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    ]
