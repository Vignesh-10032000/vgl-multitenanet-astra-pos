"""Checkout, quote, sale, and offline-sync contracts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from vglpos.api.v1.schemas.common import Money, Qty, RequestModel, ResponseModel

PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


class SaleQuery(RequestModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=500)
    limit: int = Field(default=50, ge=1, le=200)
    start_date: date | None = None
    end_date: date | None = None
    cashier_id: int | None = Field(default=None, gt=0)
    status: Literal["COMPLETED", "CANCELLED", "PARTIALLY_RETURNED", "RETURNED"] | None = None


class CheckoutLineRequest(RequestModel):
    product_id: int = Field(gt=0)
    quantity: Qty
    line_discount: Money = Decimal("0.00")


class PaymentRequest(RequestModel):
    method: Literal["CASH", "CARD", "UPI", "BANK_TRANSFER", "CREDIT", "LOYALTY", "OTHER"]
    amount: PositiveMoney
    reference_number: str | None = Field(default=None, max_length=100)


class QuoteRequest(RequestModel):
    lines: list[CheckoutLineRequest] = Field(min_length=1, max_length=200)
    customer_id: int | None = Field(default=None, gt=0)
    business_date: date = Field(default_factory=date.today)
    order_discount: Money = Decimal("0.00")
    apply_round_off: bool = True


class PaymentPreviewRequest(QuoteRequest):
    payments: list[PaymentRequest] = Field(min_length=1, max_length=5)


class CheckoutRequest(QuoteRequest):
    payments: list[PaymentRequest] = Field(min_length=1, max_length=5)
    shift_id: int | None = Field(default=None, gt=0)
    offline_uuid: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


class OfflineCheckoutRequest(CheckoutRequest):
    offline_uuid: UUID


class OfflinePushRequest(RequestModel):
    sales: list[OfflineCheckoutRequest] = Field(min_length=1, max_length=100)


class OfflineOperationRequest(RequestModel):
    uuid: UUID
    sale: OfflineCheckoutRequest
    signature: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")

    @model_validator(mode="after")
    def _matching_uuid(self) -> OfflineOperationRequest:
        if self.uuid != self.sale.offline_uuid:
            raise ValueError("Operation UUID must match sale.offline_uuid")
        return self


class OfflineBatchRequest(RequestModel):
    operations: list[OfflineOperationRequest] = Field(min_length=1, max_length=100)


class OfflineBootstrapResponse(ResponseModel):
    terminal_code: str
    supplier_state: str
    signing_key: str
    signing_algorithm: Literal["HMAC-SHA-256"] = "HMAC-SHA-256"
    outbox_limit: int = 500


class VoidSaleRequest(RequestModel):
    reason: str = Field(min_length=1, max_length=500)
    approver_user_id: int = Field(gt=0)
    approval_pin: str = Field(pattern=r"^\d{4,6}$")


class ReceiptDispatchRequest(RequestModel):
    """Require an explicit empty JSON object for receipt dispatch."""


class SaleLineResponse(ResponseModel):
    id: int
    product_id: int
    sku: str
    name: str
    name_en: str | None
    name_ta: str | None
    line_number: int
    quantity: Decimal
    unit_price: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    total_amount: Decimal


class SalePaymentResponse(ResponseModel):
    id: int
    payment_method: str
    amount: Decimal
    reference_number: str | None
    loyalty_points: Decimal | None


class EInvoiceReceiptResponse(ResponseModel):
    status: str
    irn: str | None
    ack_number: str | None
    ack_date: datetime | None
    qr_data_uri: str | None


class SaleResponse(ResponseModel):
    id: int
    invoice_number: str
    business_date: date
    sale_status: str
    supply_type: str
    customer_id: int | None
    cashier_id: int
    branch_id: int
    terminal_id: int
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    round_off: Decimal
    net_amount: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    payment_method: str
    created_at: datetime


class SaleDetailResponse(SaleResponse):
    items: list[SaleLineResponse]
    payments: list[SalePaymentResponse]
    e_invoice: EInvoiceReceiptResponse | None
    composition_declaration: str | None


class SalePageResponse(ResponseModel):
    items: list[SaleResponse]
    next_cursor: str | None


class OfflineOperationResult(ResponseModel):
    uuid: UUID
    status: Literal["synced", "retry", "failed"]
    sale: SaleResponse | None = None
    error_type: str | None = None
    detail: str | None = None


class OfflineBatchResponse(ResponseModel):
    results: list[OfflineOperationResult]


class QuoteLineResponse(ResponseModel):
    quantity: Decimal
    unit_price: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_rate: Decimal
    cess_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    total_amount: Decimal


class QuoteResponse(ResponseModel):
    lines: list[QuoteLineResponse]
    is_interstate: bool
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    round_off: Decimal
    net_amount: Decimal


class PaymentPreviewResponse(QuoteResponse):
    amount_received: Decimal
    change_due: Decimal
    balance_due: Decimal


class OfflinePushResponse(ResponseModel):
    sales: list[SaleResponse]


class ReceiptDispatchResponse(ResponseModel):
    status: str
    task_id: str
