"""Domain event payloads emitted by later service-layer phases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SaleCompleted:
    """Records that a fiscal sale committed successfully."""

    company_id: int
    branch_id: int
    sale_id: int
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class StockDepleted:
    """Records that a branch/product stock balance reached zero."""

    company_id: int
    branch_id: int
    product_id: int
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ShiftClosed:
    """Records a completed cash-drawer reconciliation."""

    company_id: int
    branch_id: int
    shift_id: int
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class PriceOverridden:
    """Records an authorised product price override without exposing PII."""

    company_id: int
    product_id: int
    user_id: int
    old_price: Decimal
    new_price: Decimal
    occurred_at: datetime
