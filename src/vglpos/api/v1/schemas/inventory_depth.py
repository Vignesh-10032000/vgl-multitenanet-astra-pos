"""Deep-inventory workflow request and response contracts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from vglpos.api.v1.schemas.common import Money, NonNegativeQty, Qty, RequestModel, ResponseModel


class VariantCreateRequest(RequestModel):
    parent_product_id: int = Field(gt=0)
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    selling_price: Money
    mrp: Money
    barcode: str | None = Field(default=None, max_length=64)
    size: str | None = Field(default=None, max_length=50)
    colour: str | None = Field(default=None, max_length=50)
    style: str | None = Field(default=None, max_length=100)


class VariantResponse(ResponseModel):
    id: int
    parent_product_id: int | None
    sku: str
    name: str
    barcode: str | None
    size: str | None = Field(validation_alias="variant_size")
    colour: str | None = Field(validation_alias="variant_colour")
    style: str | None = Field(validation_alias="variant_style")
    brand: str | None
    hsn_id: int | None
    tax_rate_id: int
    selling_price: Decimal
    mrp: Decimal


class NearExpiryQuery(RequestModel):
    on_date: date
    days: int | None = Field(default=None, ge=0, le=3650)


class NearExpiryResponse(ResponseModel):
    batch_id: int
    product_id: int
    batch_number: str
    expiry_date: date
    quantity_available: Decimal
    days_remaining: int
    expired: bool


class NearExpiryListResponse(ResponseModel):
    items: list[NearExpiryResponse]


class CountSheetCreateRequest(RequestModel):
    product_ids: list[int] | None = Field(default=None, max_length=5000)


class StockCountLineRequest(RequestModel):
    stock_audit_item_id: int = Field(gt=0)
    counted_quantity: NonNegativeQty
    reason: str | None = Field(default=None, max_length=1000)


class StockCountRequest(RequestModel):
    lines: list[StockCountLineRequest] = Field(min_length=1, max_length=5000)


class StockAuditResponse(ResponseModel):
    id: int
    branch_id: int
    audit_number: str
    status: str
    counted_at: datetime | None
    posted_at: datetime | None


class TransferLineRequest(RequestModel):
    product_id: int = Field(gt=0)
    quantity: Qty
    source_batch_id: int | None = Field(default=None, gt=0)


class TransferCreateRequest(RequestModel):
    destination_branch_id: int = Field(gt=0)
    transfer_date: date
    notes: str | None = None
    lines: list[TransferLineRequest] = Field(min_length=1, max_length=500)


class StockTransferResponse(ResponseModel):
    id: int
    source_branch_id: int
    destination_branch_id: int
    transfer_number: str
    status: str
    dispatched_at: datetime | None
    received_at: datetime | None


class ReorderQuery(RequestModel):
    as_of: date
    sales_days: int = Field(default=30, ge=1, le=3650)


class ReorderResponse(ResponseModel):
    product_id: int
    sku: str
    on_hand: Decimal
    daily_velocity: Decimal
    lead_time_days: int
    safety_stock: Decimal
    suggested_quantity: Decimal


class ReorderListResponse(ResponseModel):
    items: list[ReorderResponse]


class StockValueResponse(ResponseModel):
    product_id: int
    sku: str
    quantity: Decimal
    cost_value: Decimal
    retail_value: Decimal


class StockValueListResponse(ResponseModel):
    items: list[StockValueResponse]
    total_cost_value: Decimal
    total_retail_value: Decimal
