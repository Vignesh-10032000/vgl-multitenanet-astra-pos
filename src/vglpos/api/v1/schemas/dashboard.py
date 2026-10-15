"""Typed overview contracts for the current dashboard."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from vglpos.api.v1.schemas.common import RequestModel, ResponseModel
from vglpos.api.v1.schemas.reports import DailySummaryResponse, RevenuePointResponse


class DashboardQuery(RequestModel):
    on_date: date = Field(default_factory=date.today)


class DashboardProductResponse(ResponseModel):
    product_id: int
    sku: str
    name: str
    name_en: str | None
    name_ta: str | None
    quantity: Decimal
    revenue: Decimal


class DashboardStockResponse(ResponseModel):
    product_id: int
    sku: str
    name: str
    name_en: str | None
    name_ta: str | None
    quantity: Decimal
    threshold: Decimal


class DashboardSaleResponse(ResponseModel):
    id: int
    invoice_number: str
    customer_name: str | None
    item_quantity: Decimal
    created_at: datetime
    payment_method: str
    sale_status: str
    net_amount: Decimal


class DashboardPaymentResponse(ResponseModel):
    payment_method: str
    transaction_count: int
    amount: Decimal


class DashboardOverviewResponse(ResponseModel):
    on_date: date
    summary: DailySummaryResponse
    week_sales: Decimal
    month_sales: Decimal
    average_bill: Decimal
    total_products: int
    total_customers: int
    low_stock_count: int
    revenue: list[RevenuePointResponse]
    top_products: list[DashboardProductResponse]
    low_stock: list[DashboardStockResponse]
    payment_mix: list[DashboardPaymentResponse]
    recent_sales: list[DashboardSaleResponse]
