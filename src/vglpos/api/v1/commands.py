"""Translate validated API DTOs into service-layer commands."""

from __future__ import annotations

from vglpos.api.v1.context import CounterContext
from vglpos.api.v1.schemas.sales import CheckoutRequest, QuoteRequest
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    PaymentCommand,
    QuoteCommand,
)


def checkout_command(body: CheckoutRequest, context: CounterContext) -> CheckoutCommand:
    """Build checkout facts exclusively from validated input and JWT context."""
    return CheckoutCommand(
        company_id=context.company_id,
        branch_id=context.branch_id,
        terminal_id=context.terminal_id,
        cashier_id=context.user_id,
        lines=checkout_lines(body),
        payments=[
            PaymentCommand(payment.method, payment.amount, payment.reference_number)
            for payment in body.payments
        ],
        customer_id=body.customer_id,
        shift_id=body.shift_id,
        offline_uuid=str(body.offline_uuid) if body.offline_uuid is not None else None,
        business_date=body.business_date,
        order_discount=body.order_discount,
        apply_round_off=body.apply_round_off,
        notes=body.notes,
    )


def quote_command(body: QuoteRequest, context: CounterContext) -> QuoteCommand:
    """Build a non-persisting pricing command from validated request facts."""
    return QuoteCommand(
        company_id=context.company_id,
        branch_id=context.branch_id,
        lines=checkout_lines(body),
        customer_id=body.customer_id,
        business_date=body.business_date,
        order_discount=body.order_discount,
        apply_round_off=body.apply_round_off,
    )


def checkout_lines(body: QuoteRequest) -> list[CheckoutLineCommand]:
    """Map bounded cart lines without accepting any client price or tax fact."""
    return [
        CheckoutLineCommand(
            product_id=line.product_id,
            quantity=line.quantity,
            line_discount=line.line_discount,
        )
        for line in body.lines
    ]
