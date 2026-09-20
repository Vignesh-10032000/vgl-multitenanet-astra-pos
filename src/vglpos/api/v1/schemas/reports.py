"""Operational and GST report response contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from vglpos.api.v1.schemas.common import RequestModel, ResponseModel


class DailySummaryQuery(RequestModel):
    on_date: date


class DateRangeQuery(RequestModel):
    start_date: date
    end_date: date


class RevenueQuery(RequestModel):
    days: int = Field(default=7, ge=1, le=3660)


class InventoryValuationQuery(RequestModel):
    method: Literal["WEIGHTED_AVERAGE", "FIFO"] = "WEIGHTED_AVERAGE"


class DailySummaryResponse(ResponseModel):
    total_bills: int
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    round_off: Decimal
    net_amount: Decimal


class RevenuePointResponse(ResponseModel):
    business_date: date
    total_bills: int
    net_amount: Decimal


class RevenueSeriesResponse(ResponseModel):
    items: list[RevenuePointResponse]


class Gstr1RowResponse(ResponseModel):
    table: str
    invoice_number: str
    business_date: date
    customer_gstin: str | None
    place_of_supply: str | None
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    invoice_value: Decimal


class Gstr1Response(ResponseModel):
    items: list[Gstr1RowResponse]


class InventoryValuationRowResponse(ResponseModel):
    product_id: int
    sku: str
    name: str
    quantity: Decimal
    unit_cost: Decimal
    value: Decimal


class InventoryValuationResponse(ResponseModel):
    method: str
    items: list[InventoryValuationRowResponse]
    total_value: Decimal
