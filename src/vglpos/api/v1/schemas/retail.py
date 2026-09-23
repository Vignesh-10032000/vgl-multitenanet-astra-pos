"""Held-bill and terminal quick-key API contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from vglpos.api.v1.schemas.common import Money, RequestModel, ResponseModel
from vglpos.api.v1.schemas.products import ProductResponse
from vglpos.api.v1.schemas.sales import CheckoutLineRequest


class HoldBillRequest(RequestModel):
    shift_id: int = Field(gt=0)
    label: str | None = Field(default=None, max_length=100)
    lines: list[CheckoutLineRequest] = Field(min_length=1, max_length=200)
    customer_id: int | None = Field(default=None, gt=0)
    order_discount: Money = Decimal("0.00")
    apply_round_off: bool = True


class HeldBillResponse(ResponseModel):
    id: int
    shift_id: int
    label: str | None
    cart_payload: dict[str, object]
    item_count: int
    net_amount: Decimal
    status: str
    created_at: datetime
    stock_reserved: bool = False


class HeldBillListResponse(ResponseModel):
    items: list[HeldBillResponse]
    stock_notice: str = "Held bills do not reserve stock."


class QuickKeyAssignmentRequest(RequestModel):
    key_number: int = Field(ge=1, le=12)
    product_id: int = Field(gt=0)


class ConfigureQuickKeysRequest(RequestModel):
    assignments: list[QuickKeyAssignmentRequest] = Field(max_length=12)


class QuickKeyResponse(ResponseModel):
    key_number: int
    is_pinned: bool
    product: ProductResponse


class QuickKeyListResponse(ResponseModel):
    items: list[QuickKeyResponse]
