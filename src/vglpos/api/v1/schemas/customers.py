"""Customer API contracts."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from vglpos.api.v1.schemas.common import CursorQuery, Money, RequestModel, ResponseModel
from vglpos.api.v1.schemas.sales import SaleResponse


class CustomerQuery(CursorQuery):
    q: str | None = Field(default=None, min_length=1, max_length=255)


class CustomerCreateRequest(RequestModel):
    phone: str = Field(min_length=5, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    state_code: str = Field(default="33", pattern=r"^\d{2}$")
    credit_limit: Money = Decimal("0.00")
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")


class CustomerResponse(ResponseModel):
    id: int
    phone: str
    name: str
    email: str | None
    gstin: str | None
    state_code: str
    loyalty_points: Decimal
    total_spent: Decimal
    total_orders: int
    credit_limit: Decimal
    outstanding_balance: Decimal
    address: str | None
    city: str | None
    postal_code: str | None
    is_active: bool


class CustomerPageResponse(ResponseModel):
    items: list[CustomerResponse]
    next_cursor: str | None


class CustomerDetailResponse(CustomerResponse):
    purchases: list[SaleResponse]
