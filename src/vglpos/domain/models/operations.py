"""Shift, cash movement, and immutable audit models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import BIGINT, TenantEntity


class Shift(TenantEntity):
    """Cash-drawer session owned by one terminal and cashier."""

    __tablename__ = "shifts"
    __table_args__ = (
        Index(
            "idx_shifts_open",
            "terminal_id",
            postgresql_where=text("status = 'OPEN'"),
            sqlite_where=text("status = 'OPEN'"),
        ),
    )

    branch_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    terminal_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("terminals.id", ondelete="RESTRICT"), nullable=False
    )
    cashier_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opening_cash: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    closing_cash_expected: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    closing_cash_counted: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cash_difference: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="OPEN", server_default=text("'OPEN'"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CashMovement(TenantEntity):
    """Auditable cash pay-in, pay-out, float, or drop within a shift."""

    __tablename__ = "cash_movements"
    shift_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class AuditLog(TenantEntity):
    """Immutable security and business audit record partitioned by creation time."""

    __tablename__ = "audit_log"
    __table_args__ = ({"postgresql_partition_by": "RANGE (created_at)"},)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), primary_key=True, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    old_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    new_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
