"""Thin supplier purchasing and payable workflow API routes."""

from __future__ import annotations

from flask import Blueprint, Response, g
from sqlalchemy.orm import Session

from vglpos.api.v1.context import counter_context
from vglpos.api.v1.http import model_response, parse_body
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.purchases import (
    GoodsReceiptCreateRequest,
    GoodsReceiptResponse,
    PurchaseInvoicePreviewResponse,
    PurchaseInvoiceRequest,
    PurchaseOrderCreateRequest,
    PurchaseOrderResponse,
    PurchaseResponse,
    PurchaseReturnRequest,
    PurchaseReturnResponse,
    SupplierCreateRequest,
    SupplierLedgerResponse,
    SupplierPaymentRequest,
    SupplierResponse,
)
from vglpos.extensions import db
from vglpos.security.decorators import require_permission
from vglpos.services.purchase_service import (
    CreateGoodsReceiptCommand,
    CreatePurchaseOrderCommand,
    GoodsReceiptLineCommand,
    PostPurchaseInvoiceCommand,
    PurchaseInvoiceLineCommand,
    PurchaseOrderLineCommand,
    PurchaseReturnCommand,
    PurchaseReturnLineCommand,
    PurchaseService,
    SupplierCommand,
    SupplierPaymentCommand,
)

purchases_bp = Blueprint("purchases", __name__, url_prefix="/api/v1/purchases")


@purchases_bp.post("/suppliers")
@require_permission("supplier.create")
@idempotent
@documented(
    summary="Create a GST-aware supplier",
    request_model=SupplierCreateRequest,
    response_model=SupplierResponse,
    success_status=201,
)
def create_supplier() -> tuple[Response, int]:
    body = parse_body(SupplierCreateRequest)
    with Session(db.engine) as session:
        supplier = PurchaseService(session, g.company_id).create_supplier(
            SupplierCommand(
                company_id=g.company_id,
                code=body.code,
                name=body.name,
                phone=body.phone,
                state_code=body.state_code,
                payment_terms_days=body.payment_terms_days,
                gstin=body.gstin,
                pan=body.pan,
                email=body.email,
                contact_person=body.contact_person,
                address=body.address,
                user_id=g.user_id,
            )
        )
        return model_response(SupplierResponse.model_validate(supplier), status=201)


@purchases_bp.post("/orders")
@require_permission("purchase.create")
@idempotent
@documented(
    summary="Create a supplier purchase order",
    request_model=PurchaseOrderCreateRequest,
    response_model=PurchaseOrderResponse,
    success_status=201,
)
def create_purchase_order() -> tuple[Response, int]:
    body = parse_body(PurchaseOrderCreateRequest)
    context = counter_context()
    command = CreatePurchaseOrderCommand(
        company_id=context.company_id,
        branch_id=context.branch_id,
        terminal_id=context.terminal_id,
        supplier_id=body.supplier_id,
        user_id=context.user_id,
        order_date=body.order_date,
        expected_date=body.expected_date,
        notes=body.notes,
        lines=[
            PurchaseOrderLineCommand(line.product_id, line.quantity, line.unit_cost, line.tax_rate)
            for line in body.lines
        ],
    )
    with Session(db.engine) as session:
        order = PurchaseService(session, context.company_id).create_purchase_order(command)
        return model_response(PurchaseOrderResponse.model_validate(order), status=201)


@purchases_bp.post("/receipts")
@require_permission("purchase.receive")
@idempotent
@documented(
    summary="Receive a purchase order into a GRN",
    request_model=GoodsReceiptCreateRequest,
    response_model=GoodsReceiptResponse,
    success_status=201,
)
def receive_goods() -> tuple[Response, int]:
    body = parse_body(GoodsReceiptCreateRequest)
    context = counter_context()
    command = CreateGoodsReceiptCommand(
        company_id=context.company_id,
        branch_id=context.branch_id,
        terminal_id=context.terminal_id,
        purchase_order_id=body.purchase_order_id,
        user_id=context.user_id,
        received_at=body.received_at,
        notes=body.notes,
        lines=[
            GoodsReceiptLineCommand(
                line.purchase_order_item_id,
                line.quantity,
                line.unit_cost,
                line.batch_number,
                line.mfg_date,
                line.expiry_date,
            )
            for line in body.lines
        ],
    )
    with Session(db.engine) as session:
        receipt = PurchaseService(session, context.company_id).receive_goods(command)
        return model_response(GoodsReceiptResponse.model_validate(receipt), status=201)


def _invoice_command(body: PurchaseInvoiceRequest) -> PostPurchaseInvoiceCommand:
    context = counter_context()
    return PostPurchaseInvoiceCommand(
        company_id=context.company_id,
        branch_id=context.branch_id,
        goods_receipt_id=body.goods_receipt_id,
        supplier_invoice_number=body.supplier_invoice_number,
        invoice_date=body.invoice_date,
        user_id=context.user_id,
        landed_cost=body.landed_cost,
        landed_cost_method=body.landed_cost_method,
        lines=[
            PurchaseInvoiceLineCommand(
                line.goods_receipt_item_id, line.billed_quantity, line.unit_cost
            )
            for line in body.lines
        ],
    )


@purchases_bp.post("/invoices/preview")
@require_permission("purchase.invoice")
@idempotent
@documented(
    summary="Preview supplier invoice matching and weighted-cost changes",
    request_model=PurchaseInvoiceRequest,
    response_model=PurchaseInvoicePreviewResponse,
)
def preview_purchase_invoice() -> tuple[Response, int]:
    command = _invoice_command(parse_body(PurchaseInvoiceRequest))
    with Session(db.engine) as session:
        preview = PurchaseService(session, command.company_id).preview_invoice(command)
        return model_response(PurchaseInvoicePreviewResponse.model_validate(preview))


@purchases_bp.post("/invoices")
@require_permission("purchase.invoice")
@idempotent
@documented(
    summary="Post a matched supplier invoice",
    request_model=PurchaseInvoiceRequest,
    response_model=PurchaseResponse,
    success_status=201,
)
def post_purchase_invoice() -> tuple[Response, int]:
    command = _invoice_command(parse_body(PurchaseInvoiceRequest))
    with Session(db.engine) as session:
        purchase = PurchaseService(session, command.company_id).post_invoice(command)
        return model_response(PurchaseResponse.model_validate(purchase), status=201)


@purchases_bp.post("/returns")
@require_permission("purchase.return")
@idempotent
@documented(
    summary="Create a purchase debit note",
    request_model=PurchaseReturnRequest,
    response_model=PurchaseReturnResponse,
    success_status=201,
)
def create_purchase_return() -> tuple[Response, int]:
    body = parse_body(PurchaseReturnRequest)
    context = counter_context()
    command = PurchaseReturnCommand(
        company_id=context.company_id,
        branch_id=context.branch_id,
        terminal_id=context.terminal_id,
        purchase_id=body.purchase_id,
        user_id=context.user_id,
        return_date=body.return_date,
        reason=body.reason,
        lines=[
            PurchaseReturnLineCommand(line.purchase_item_id, line.quantity) for line in body.lines
        ],
    )
    with Session(db.engine) as session:
        purchase_return = PurchaseService(session, context.company_id).create_purchase_return(
            command
        )
        return model_response(PurchaseReturnResponse.model_validate(purchase_return), status=201)


@purchases_bp.post("/supplier-payments")
@require_permission("supplier.pay")
@idempotent
@documented(
    summary="Record a supplier payment",
    request_model=SupplierPaymentRequest,
    response_model=SupplierLedgerResponse,
    success_status=201,
)
def supplier_payment() -> tuple[Response, int]:
    body = parse_body(SupplierPaymentRequest)
    movement = SupplierPaymentCommand(
        company_id=g.company_id,
        supplier_id=body.supplier_id,
        user_id=g.user_id,
        payment_date=body.payment_date,
        amount=body.amount,
        reference=body.reference,
        notes=body.notes,
    )
    with Session(db.engine) as session:
        ledger = PurchaseService(session, g.company_id).record_supplier_payment(movement)
        return model_response(SupplierLedgerResponse.model_validate(ledger), status=201)
