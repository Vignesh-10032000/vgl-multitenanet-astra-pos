"""Cash-drawer shift contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from vglpos.api.v1.schemas.common import Money, RequestModel, ResponseModel


class OpenShiftRequest(RequestModel):
    opening_cash: Money
    notes: str | None = Field(default=None, max_length=1000)


class CashMovementRequest(RequestModel):
    shift_id: int = Field(gt=0)
    movement_type: Literal["PAY_IN", "FLOAT", "CASH_IN", "PAY_OUT", "DROP", "CASH_OUT"]
    amount: Money = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class CloseShiftRequest(RequestModel):
    shift_id: int = Field(gt=0)
    counted_cash: Money
    notes: str | None = Field(default=None, max_length=1000)


class ShiftResponse(ResponseModel):
    id: int
    branch_id: int
    terminal_id: int
    cashier_id: int
    opened_at: datetime
    closed_at: datetime | None
    opening_cash: Decimal
    closing_cash_expected: Decimal | None
    closing_cash_counted: Decimal | None
    cash_difference: Decimal | None
    status: str
    notes: str | None


class CashMovementResponse(ResponseModel):
    id: int
    shift_id: int
    movement_type: str
    amount: Decimal
    reason: str
