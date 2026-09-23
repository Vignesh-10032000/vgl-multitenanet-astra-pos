"""Cash-drawer shift contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from vglpos.api.v1.schemas.common import Money, RequestModel, ResponseModel


class OpenShiftRequest(RequestModel):
    opening_cash: Money
    denomination_counts: dict[str, int]
    notes: str | None = Field(default=None, max_length=1000)


class CashMovementRequest(RequestModel):
    shift_id: int = Field(gt=0)
    movement_type: Literal["PAY_IN", "PAY_OUT", "DROP", "FLOAT_ADD"]
    amount: Money = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class CloseShiftRequest(RequestModel):
    shift_id: int = Field(gt=0)
    counted_cash: Money
    denomination_counts: dict[str, int]
    notes: str | None = Field(default=None, max_length=1000)
    approver_user_id: int | None = Field(default=None, gt=0)
    approval_pin: str | None = Field(default=None, pattern=r"^\d{4,6}$")
    variance_reason: str | None = Field(default=None, min_length=1, max_length=500)
    expire_held_bills: bool = False


class NoSaleRequest(RequestModel):
    shift_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


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
    opening_denominations: dict[str, int]
    closing_denominations: dict[str, int] | None
    variance_approved_by: int | None
    variance_reason: str | None


class CashMovementResponse(ResponseModel):
    id: int
    shift_id: int
    movement_type: str
    amount: Decimal
    reason: str


class CurrentShiftResponse(ResponseModel):
    shift: ShiftResponse | None


class ZReportResponse(ResponseModel):
    shift_id: int
    gross_sales: Decimal
    net_sales: Decimal
    transaction_count: int
    cash_sales: Decimal
    cash_movements: Decimal
    expected_cash: Decimal
    counted_cash: Decimal | None
    variance: Decimal | None
    payment_totals: dict[str, Decimal]
    discount_total: Decimal
    void_count: int
    void_total: Decimal
    return_count: int
    return_total: Decimal
    no_sale_count: int
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
