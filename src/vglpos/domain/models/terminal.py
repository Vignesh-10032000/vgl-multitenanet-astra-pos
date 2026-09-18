"""Checkout terminal model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import BIGINT, TenantEntity


class Terminal(TenantEntity):
    """Named checkout counter within a physical branch."""

    __tablename__ = "terminals"
    __table_args__ = (
        Index(
            "uq_terminals_branch_code",
            "branch_id",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_terminals_branch_id", "branch_id"),
        Index("idx_terminals_company_id", "company_id"),
    )

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    terminal_type: Mapped[str] = mapped_column(
        String(50), default="COUNTER", server_default=text("'COUNTER'"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
