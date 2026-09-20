"""Product catalogue request and response contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from vglpos.api.v1.schemas.common import (
    CursorQuery,
    Money,
    NonNegativeQty,
    RequestModel,
    ResponseModel,
)


class ProductQuery(CursorQuery):
    q: str | None = Field(default=None, min_length=1, max_length=255)
    barcode: str | None = Field(default=None, min_length=1, max_length=64)


class ProductLookupQuery(RequestModel):
    barcode: str = Field(min_length=1, max_length=64)


class ProductCreateRequest(RequestModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category_id: int | None = Field(default=None, gt=0)
    hsn_id: int | None = Field(default=None, gt=0)
    tax_rate_id: int = Field(gt=0)
    barcode: str | None = Field(default=None, min_length=1, max_length=64)
    uom: str = Field(default="UNIT", min_length=1, max_length=20)
    cost_price: Money
    selling_price: Money
    mrp: Money
    is_tax_inclusive: bool = False
    is_inventory_tracked: bool = True
    low_stock_threshold: NonNegativeQty = Decimal("5.000")
    allow_negative_stock: bool = False
    is_active: bool = True


class ProductUpdateRequest(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category_id: int | None = Field(default=None, gt=0)
    hsn_id: int | None = Field(default=None, gt=0)
    tax_rate_id: int | None = Field(default=None, gt=0)
    barcode: str | None = Field(default=None, min_length=1, max_length=64)
    uom: str | None = Field(default=None, min_length=1, max_length=20)
    cost_price: Money | None = None
    selling_price: Money | None = None
    mrp: Money | None = None
    is_tax_inclusive: bool | None = None
    is_inventory_tracked: bool | None = None
    low_stock_threshold: NonNegativeQty | None = None
    allow_negative_stock: bool | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _require_change(self) -> ProductUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("At least one product field is required.")
        return self


class ProductResponse(ResponseModel):
    id: int
    sku: str
    name: str
    description: str | None
    category_id: int | None
    hsn_id: int | None
    tax_rate_id: int
    barcode: str | None
    uom: str
    cost_price: Decimal
    selling_price: Decimal
    mrp: Decimal
    is_tax_inclusive: bool
    is_inventory_tracked: bool
    low_stock_threshold: Decimal
    on_hand: Decimal
    reserved_quantity: Decimal
    allow_negative_stock: bool
    is_active: bool
    row_version: int
    updated_at: datetime


class ProductPageResponse(ResponseModel):
    items: list[ProductResponse]
    next_cursor: str | None
