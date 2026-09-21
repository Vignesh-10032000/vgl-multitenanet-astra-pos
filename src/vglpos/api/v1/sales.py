"""Thin sale, quote, cancellation, and receipt API routes."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, g
from sqlalchemy.orm import Session

from vglpos.api.v1.commands import checkout_command, payment_preview_command, quote_command
from vglpos.api.v1.context import counter_context
from vglpos.api.v1.http import model_response, parse_body, parse_query
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.sales import (
    CheckoutRequest,
    PaymentPreviewRequest,
    PaymentPreviewResponse,
    QuoteRequest,
    QuoteResponse,
    ReceiptDispatchRequest,
    ReceiptDispatchResponse,
    SaleDetailResponse,
    SalePageResponse,
    SaleQuery,
    SaleResponse,
    VoidSaleRequest,
)
from vglpos.api.v1.serializers import (
    payment_preview_response,
    quote_response,
    sale_detail_response,
    sale_response,
)
from vglpos.extensions import db, limiter
from vglpos.security.decorators import require_permission
from vglpos.services.checkout_service import CheckoutService
from vglpos.services.exceptions import ValidationError
from vglpos.services.sales_service import CancelSaleCommand, SalesService
from vglpos.tasks.receipts import send_whatsapp_receipt

sales_bp = Blueprint("sales", __name__, url_prefix="/api/v1/sales")


def _terminal_rate_key() -> str:
    return f"{g.company_id}:{g.terminal_id}"


def _user_rate_key() -> str:
    return f"{g.company_id}:{g.user_id}"


@sales_bp.post("/checkout")
@require_permission("sale.create")
@limiter.limit("120 per minute", key_func=_terminal_rate_key)
@idempotent
@documented(
    summary="Complete an authoritative server-priced checkout",
    request_model=CheckoutRequest,
    response_model=SaleResponse,
    success_status=201,
)
def checkout() -> tuple[Response, int]:
    body = parse_body(CheckoutRequest)
    with Session(db.engine) as session:
        sale = CheckoutService(session).checkout(checkout_command(body, counter_context()))
        return model_response(sale_response(sale), status=201)


@sales_bp.post("/quote")
@require_permission("sale.create")
@limiter.limit("120 per minute", key_func=_terminal_rate_key)
@idempotent
@documented(
    summary="Calculate a cart without persisting it",
    request_model=QuoteRequest,
    response_model=QuoteResponse,
)
def quote() -> tuple[Response, int]:
    body = parse_body(QuoteRequest)
    with Session(db.engine) as session:
        command = quote_command(body, counter_context())
        return model_response(quote_response(CheckoutService(session).quote(command)))


@sales_bp.post("/payment-preview")
@require_permission("sale.create")
@limiter.limit("120 per minute", key_func=_terminal_rate_key)
@idempotent
@documented(
    summary="Calculate exact split-tender balance and cash-funded change",
    request_model=PaymentPreviewRequest,
    response_model=PaymentPreviewResponse,
)
def payment_preview() -> tuple[Response, int]:
    """Delegate non-persisting payment validation to checkout's money rules."""
    body = parse_body(PaymentPreviewRequest)
    with Session(db.engine) as session:
        command = payment_preview_command(body, counter_context())
        preview = CheckoutService(session).preview_payment(command)
        return model_response(payment_preview_response(preview))


@sales_bp.get("")
@require_permission("sale.view")
@documented(
    summary="List tenant sales with keyset pagination",
    query_model=SaleQuery,
    response_model=SalePageResponse,
)
def list_sales() -> tuple[Response, int]:
    query = parse_query(SaleQuery)
    with Session(db.engine) as session:
        page = SalesService(session, g.company_id, branch_id=g.branch_id).list_sales(
            cursor=query.cursor,
            limit=query.limit,
            branch_id=g.branch_id,
            start_date=query.start_date,
            end_date=query.end_date,
            cashier_id=query.cashier_id,
            status=query.status,
        )
        response = SalePageResponse(
            items=[sale_response(sale) for sale in page.items], next_cursor=page.next_cursor
        )
        return model_response(response)


@sales_bp.get("/<int:sale_id>")
@require_permission("sale.view")
@documented(summary="Get a complete invoice", response_model=SaleDetailResponse)
def get_sale(sale_id: int) -> tuple[Response, int]:
    with Session(db.engine) as session:
        detail = SalesService(session, g.company_id, branch_id=g.branch_id).sale_detail(sale_id)
        return model_response(sale_detail_response(detail))


@sales_bp.post("/<int:sale_id>/cancel")
@require_permission("sale.void")
@idempotent
@documented(
    summary="Void a completed sale with manager approval",
    request_model=VoidSaleRequest,
    response_model=SaleResponse,
)
def cancel_sale(sale_id: int) -> tuple[Response, int]:
    body = parse_body(VoidSaleRequest)
    command = CancelSaleCommand(
        company_id=g.company_id,
        actor_user_id=g.user_id,
        sale_id=sale_id,
        reason=body.reason,
        approver_user_id=body.approver_user_id,
        approval_pin=body.approval_pin,
    )
    with Session(db.engine) as session:
        sale = SalesService(session, g.company_id, branch_id=g.branch_id).cancel_sale(command)
        return model_response(sale_response(sale))


@sales_bp.post("/<int:sale_id>/receipt/whatsapp")
@require_permission("sale.view")
@limiter.limit("5 per hour", key_func=_user_rate_key)
@idempotent
@documented(
    summary="Queue a WhatsApp receipt delivery",
    request_model=ReceiptDispatchRequest,
    response_model=ReceiptDispatchResponse,
    success_status=202,
)
def send_receipt(sale_id: int) -> tuple[Response, int]:
    parse_body(ReceiptDispatchRequest)
    base_url = str(current_app.config["PUBLIC_RECEIPT_BASE_URL"]).strip().rstrip("/")
    if not all(
        (
            base_url,
            current_app.config["WHATSAPP_WEBHOOK_URL"],
            current_app.config["WHATSAPP_API_TOKEN"],
        )
    ):
        raise ValidationError("WhatsApp receipt delivery is not configured.")
    with Session(db.engine) as session:
        dispatch = SalesService(session, g.company_id, branch_id=g.branch_id).receipt_dispatch(
            sale_id
        )
    task = send_whatsapp_receipt.apply_async(
        kwargs={
            "phone": dispatch.phone,
            "invoice_number": dispatch.invoice_number,
            "receipt_url": f"{base_url}/{dispatch.sale_id}",
        }
    )
    return model_response(
        ReceiptDispatchResponse(status="queued", task_id=str(task.id)), status=202
    )
