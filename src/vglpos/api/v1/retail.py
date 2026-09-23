"""Counter operations for held carts and keyboard quick keys."""

from __future__ import annotations

from flask import Blueprint, Response
from sqlalchemy.orm import Session

from vglpos.api.v1.context import counter_context
from vglpos.api.v1.http import model_response, parse_body
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.retail import (
    ConfigureQuickKeysRequest,
    HeldBillListResponse,
    HeldBillResponse,
    HoldBillRequest,
    QuickKeyListResponse,
    QuickKeyResponse,
)
from vglpos.api.v1.serializers import product_response
from vglpos.extensions import db
from vglpos.security.decorators import require_permission
from vglpos.services.checkout_service import CheckoutLineCommand
from vglpos.services.retail_operations_service import (
    ConfigureQuickKeysCommand,
    HoldBillCommand,
    QuickKeyAssignment,
    RetailOperationsService,
)

retail_bp = Blueprint("retail", __name__, url_prefix="/api/v1/retail")


def _held_response(held: object) -> HeldBillResponse:
    return HeldBillResponse.model_validate(held)


def _quick_key_response(entry: object) -> QuickKeyResponse:
    return QuickKeyResponse(
        key_number=entry.key_number,
        is_pinned=entry.is_pinned,
        product=product_response(entry.product),
    )


@retail_bp.post("/held-bills")
@require_permission("sale.create")
@idempotent
@documented(
    summary="Park a server-priced cart without reserving stock",
    request_model=HoldBillRequest,
    response_model=HeldBillResponse,
    success_status=201,
)
def hold_bill() -> tuple[Response, int]:
    body = parse_body(HoldBillRequest)
    context = counter_context()
    command = HoldBillCommand(
        company_id=context.company_id,
        branch_id=context.branch_id,
        terminal_id=context.terminal_id,
        cashier_id=context.user_id,
        shift_id=body.shift_id,
        label=body.label,
        lines=[
            CheckoutLineCommand(line.product_id, line.quantity, line.line_discount)
            for line in body.lines
        ],
        customer_id=body.customer_id,
        order_discount=body.order_discount,
        apply_round_off=body.apply_round_off,
    )
    with Session(db.engine) as session:
        held = RetailOperationsService(session).hold_bill(command)
        return model_response(_held_response(held), status=201)


@retail_bp.get("/held-bills")
@require_permission("sale.create")
@documented(summary="List unresolved held bills", response_model=HeldBillListResponse)
def list_held_bills() -> tuple[Response, int]:
    context = counter_context()
    with Session(db.engine) as session:
        items = RetailOperationsService(session).list_held_bills(
            context.company_id, context.branch_id, context.terminal_id
        )
        return model_response(HeldBillListResponse(items=[_held_response(item) for item in items]))


@retail_bp.post("/held-bills/<int:held_bill_id>/recall")
@require_permission("sale.create")
@idempotent
@documented(summary="Recall one held bill", response_model=HeldBillResponse)
def recall_held_bill(held_bill_id: int) -> tuple[Response, int]:
    context = counter_context()
    with Session(db.engine) as session:
        held = RetailOperationsService(session).recall_bill(
            company_id=context.company_id,
            branch_id=context.branch_id,
            terminal_id=context.terminal_id,
            cashier_id=context.user_id,
            held_bill_id=held_bill_id,
        )
        return model_response(_held_response(held))


@retail_bp.delete("/held-bills/<int:held_bill_id>")
@require_permission("sale.create")
@documented(summary="Discard one held bill", response_model=HeldBillResponse)
def discard_held_bill(held_bill_id: int) -> tuple[Response, int]:
    context = counter_context()
    with Session(db.engine) as session:
        held = RetailOperationsService(session).discard_bill(
            company_id=context.company_id,
            branch_id=context.branch_id,
            terminal_id=context.terminal_id,
            user_id=context.user_id,
            held_bill_id=held_bill_id,
        )
        return model_response(_held_response(held))


@retail_bp.get("/quick-keys")
@require_permission("product.view")
@documented(
    summary="List pinned and top-selling terminal quick keys", response_model=QuickKeyListResponse
)
def list_quick_keys() -> tuple[Response, int]:
    context = counter_context()
    with Session(db.engine) as session:
        entries = RetailOperationsService(session).list_quick_keys(
            context.company_id, context.branch_id, context.terminal_id
        )
        return model_response(
            QuickKeyListResponse(items=[_quick_key_response(entry) for entry in entries])
        )


@retail_bp.put("/quick-keys")
@require_permission("product.edit")
@idempotent
@documented(
    summary="Replace pinned terminal quick keys",
    request_model=ConfigureQuickKeysRequest,
    response_model=QuickKeyListResponse,
)
def configure_quick_keys() -> tuple[Response, int]:
    body = parse_body(ConfigureQuickKeysRequest)
    context = counter_context()
    command = ConfigureQuickKeysCommand(
        company_id=context.company_id,
        branch_id=context.branch_id,
        terminal_id=context.terminal_id,
        user_id=context.user_id,
        assignments=[
            QuickKeyAssignment(item.key_number, item.product_id) for item in body.assignments
        ],
    )
    with Session(db.engine) as session:
        entries = RetailOperationsService(session).configure_quick_keys(command)
        return model_response(
            QuickKeyListResponse(items=[_quick_key_response(entry) for entry in entries])
        )
