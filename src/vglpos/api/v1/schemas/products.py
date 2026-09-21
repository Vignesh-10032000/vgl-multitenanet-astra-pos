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


class CatalogDeltaQuery(RequestModel):
    since: datetime | None = None
    limit: int = Field(default=10000, ge=1, le=50000)


class CategoryResponse(ResponseModel):
    id: int
    name: str
    name_en: str | None
    name_ta: str | None
    icon: str | None


class CategoryListResponse(ResponseModel):
    items: list[CategoryResponse]


class ProductCreateRequest(RequestModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    name_en: str | None = Field(default=None, min_length=1, max_length=255)
    name_ta: str | None = Field(default=None, min_length=1, max_length=255)
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
    is_weighed: bool = False
    low_stock_threshold: NonNegativeQty = Decimal("5.000")
    allow_negative_stock: bool = False
    is_active: bool = True


class ProductUpdateRequest(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    name_en: str | None = Field(default=None, min_length=1, max_length=255)
    name_ta: str | None = Field(default=None, min_length=1, max_length=255)
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
    is_weighed: bool | None = None
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
    name_en: str | None
    name_ta: str | None
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
    is_weighed: bool
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


class CatalogProductResponse(ProductResponse):
    tax_rate: Decimal
    cess_rate: Decimal
    deleted_at: datetime | None


class CatalogDeltaResponse(ResponseModel):
    items: list[CatalogProductResponse]
    synced_at: datetime
    truncated: bool
