"""Supplier purchase workflow request and response contracts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from vglpos.api.v1.schemas.common import Money, Qty, Rate, RequestModel, ResponseModel


class SupplierCreateRequest(RequestModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=20)
    state_code: str = Field(pattern=r"^\d{2}$")
    payment_terms_days: int = Field(default=30, ge=0, le=3650)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    pan: str | None = Field(default=None, min_length=10, max_length=10)
    email: str | None = Field(default=None, max_length=255)
    contact_person: str | None = Field(default=None, max_length=255)
    address: str | None = None


class SupplierResponse(ResponseModel):
    id: int
    code: str
    name: str
    phone: str
    state_code: str
    payment_terms_days: int
    gstin: str | None
    outstanding_balance: Decimal
    is_active: bool


class PurchaseOrderLineRequest(RequestModel):
    product_id: int = Field(gt=0)
    quantity: Qty
    unit_cost: Money
    tax_rate: Rate


class PurchaseOrderCreateRequest(RequestModel):
    supplier_id: int = Field(gt=0)
    order_date: date
    expected_date: date | None = None
    notes: str | None = None
    lines: list[PurchaseOrderLineRequest] = Field(min_length=1, max_length=500)


class PurchaseOrderResponse(ResponseModel):
    id: int
    branch_id: int
    supplier_id: int
    order_number: str
    order_date: date
    expected_date: date | None
    status: str
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class GoodsReceiptLineRequest(RequestModel):
    purchase_order_item_id: int = Field(gt=0)
    quantity: Qty
    unit_cost: Money
    batch_number: str | None = Field(default=None, max_length=100)
    mfg_date: date | None = None
    expiry_date: date | None = None


class GoodsReceiptCreateRequest(RequestModel):
    purchase_order_id: int = Field(gt=0)
    received_at: datetime
    notes: str | None = None
    lines: list[GoodsReceiptLineRequest] = Field(min_length=1, max_length=500)


class GoodsReceiptResponse(ResponseModel):
    id: int
    branch_id: int
    supplier_id: int
    purchase_order_id: int
    grn_number: str
    received_at: datetime
    status: str


class PurchaseInvoiceLineRequest(RequestModel):
    goods_receipt_item_id: int = Field(gt=0)
    billed_quantity: Qty
    unit_cost: Money


class PurchaseInvoiceRequest(RequestModel):
    goods_receipt_id: int = Field(gt=0)
    supplier_invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    lines: list[PurchaseInvoiceLineRequest] = Field(min_length=1, max_length=500)
    landed_cost: Money = Decimal("0.00")
    landed_cost_method: Literal["VALUE", "WEIGHT"] = "VALUE"


class PurchaseCostPreviewLineResponse(ResponseModel):
    goods_receipt_item_id: int
    purchase_order_item_id: int
    product_id: int
    received_quantity: Decimal
    billed_quantity: Decimal
    expected_unit_cost: Decimal
    invoice_unit_cost: Decimal
    quantity_variance_percent: Decimal
    price_variance_percent: Decimal
    landed_cost_amount: Decimal
    unit_landed_cost: Decimal
    old_average_cost: Decimal
    new_average_cost: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal


class PurchaseInvoicePreviewResponse(ResponseModel):
    supplier_id: int
    purchase_order_id: int
    goods_receipt_id: int
    lines: list[PurchaseCostPreviewLineResponse]
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    landed_cost_amount: Decimal
    total_amount: Decimal


class PurchaseResponse(ResponseModel):
    id: int
    branch_id: int
    supplier_id: int
    invoice_number: str
    invoice_date: date
    due_date: date | None
    status: str
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    landed_cost_amount: Decimal
    total_amount: Decimal
    outstanding_amount: Decimal


class PurchaseReturnLineRequest(RequestModel):
    purchase_item_id: int = Field(gt=0)
    quantity: Qty


class PurchaseReturnRequest(RequestModel):
    purchase_id: int = Field(gt=0)
    return_date: date
    reason: str = Field(min_length=1, max_length=1000)
    lines: list[PurchaseReturnLineRequest] = Field(min_length=1, max_length=500)


class PurchaseReturnResponse(ResponseModel):
    id: int
    branch_id: int
    supplier_id: int
    purchase_id: int
    debit_note_number: str
    return_date: date
    reason: str
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal


class SupplierPaymentRequest(RequestModel):
    supplier_id: int = Field(gt=0)
    payment_date: date
    amount: Money
    reference: str = Field(min_length=1, max_length=100)
    notes: str | None = None


class SupplierLedgerResponse(ResponseModel):
    id: int
    supplier_id: int
    txn_date: date
    txn_type: str
    reference_type: str
    reference_id: str
    debit_amount: Decimal
    credit_amount: Decimal
    balance_after: Decimal
