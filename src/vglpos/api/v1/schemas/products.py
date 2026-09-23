"""Product catalogue request and response contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

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
    image_path: str | None
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


class ProductImportRowResponse(ResponseModel):
    row_number: int
    sku: str
    valid: bool
    errors: list[str]


class ProductImportPreviewResponse(ResponseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[ProductImportRowResponse]


class ProductImportCommitResponse(ResponseModel):
    imported_count: int


class BulkPriceUpdateRequest(RequestModel):
    category_id: int | None = Field(default=None, gt=0)
    percentage: Decimal = Field(gt=Decimal("-100.00"), le=Decimal("1000.00"))
    approver_user_id: int = Field(gt=0)
    approval_pin: str = Field(pattern=r"^\d{4,6}$")
    reason: str = Field(min_length=1, max_length=500)


class BulkPriceUpdateResponse(ResponseModel):
    updated_count: int
    percentage: Decimal
    category_id: int | None


class BarcodeLabelsRequest(RequestModel):
    product_ids: list[int] = Field(min_length=1, max_length=100)
    symbology: Literal["AUTO", "CODE128", "EAN13"] = "AUTO"
    width_mm: Decimal = Field(default=Decimal("50.00"), ge=Decimal("25.00"), le=Decimal("100.00"))
    height_mm: Decimal = Field(default=Decimal("30.00"), ge=Decimal("15.00"), le=Decimal("75.00"))
