"""Phase 7 split tender, customer credit, and loyalty ledger tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import Customer, LoyaltyLedger, SaleItem, SalePayment
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.exceptions import InvalidPaymentError
from vglpos.services.return_service import (
    CreateCreditNoteCommand,
    ReturnLineCommand,
    ReturnService,
)

from .conftest import ServiceContext, open_service_shift


def _checkout(
    context: ServiceContext,
    payments: list[PaymentCommand],
    *,
    customer_id: int | None = None,
) -> CheckoutCommand:
    return CheckoutCommand(
        company_id=context.company.id,
        branch_id=context.branch.id,
        terminal_id=context.terminal.id,
        cashier_id=context.cashier.id,
        customer_id=customer_id,
        business_date=date(2026, 9, 22),
        lines=[CheckoutLineCommand(context.product.id, "1")],
        payments=payments,
    )


def test_split_tender_allows_change_only_from_cash(
    service_session: Session, service_context: ServiceContext
) -> None:
    open_service_shift(service_session, service_context)
    sale = CheckoutService(service_session).checkout(
        _checkout(
            service_context,
            [
                PaymentCommand("UPI", "100.00", "UPI-001"),
                PaymentCommand("CASH", "20.00"),
            ],
        )
    )

    payments = tuple(
        service_session.scalars(
            select(SalePayment).where(SalePayment.sale_id == sale.id).order_by(SalePayment.id)
        )
    )
    assert [(payment.payment_method, payment.amount) for payment in payments] == [
        ("UPI", Decimal("100.00")),
        ("CASH", Decimal("20.00")),
    ]
    with pytest.raises(InvalidPaymentError, match="non-cash"):
        CheckoutService(service_session).preview_payment(
            _checkout(service_context, [PaymentCommand("CARD", "120.00", "CARD-001")])
        )


@pytest.mark.parametrize("method", ["UPI", "CARD"])
def test_upi_and_card_require_references(
    service_session: Session, service_context: ServiceContext, method: str
) -> None:
    with pytest.raises(InvalidPaymentError, match="reference number"):
        CheckoutService(service_session).preview_payment(
            _checkout(service_context, [PaymentCommand(method, "118.00")])
        )


def test_customer_credit_limit_and_outstanding_are_enforced(
    service_session: Session, service_context: ServiceContext
) -> None:
    open_service_shift(service_session, service_context)
    service_context.customer.credit_limit = Decimal("100.00")
    service_context.customer.outstanding_balance = Decimal("80.00")
    service_session.commit()
    service = CheckoutService(service_session)

    with pytest.raises(InvalidPaymentError, match="available limit"):
        service.checkout(
            _checkout(
                service_context,
                [PaymentCommand("CREDIT", "38.00"), PaymentCommand("CASH", "80.00")],
                customer_id=service_context.customer.id,
            )
        )

    sale = service.checkout(
        _checkout(
            service_context,
            [PaymentCommand("CREDIT", "18.00"), PaymentCommand("CASH", "100.00")],
            customer_id=service_context.customer.id,
        )
    )
    customer = service_session.get(Customer, service_context.customer.id)
    assert sale.payment_method == "SPLIT"
    assert customer is not None and customer.outstanding_balance == Decimal("98.00")
    item = service_session.scalar(select(SaleItem).where(SaleItem.sale_id == sale.id))
    assert item is not None
    ReturnService(service_session).create_credit_note(
        CreateCreditNoteCommand(
            company_id=service_context.company.id,
            original_sale_id=sale.id,
            user_id=service_context.cashier.id,
            reason="CUSTOMER_REQUEST",
            on_date=date(2026, 9, 22),
            lines=[ReturnLineCommand(item.id, "1")],
        )
    )
    service_session.refresh(customer)
    assert customer.outstanding_balance == Decimal("80.00")


def test_loyalty_earn_redeem_and_return_reversal_are_all_ledgered(
    service_session: Session, service_context: ServiceContext
) -> None:
    open_service_shift(service_session, service_context)
    service_context.customer.loyalty_points = Decimal("100.000")
    service_session.commit()
    sale = CheckoutService(service_session).checkout(
        _checkout(
            service_context,
            [PaymentCommand("LOYALTY", "25.00"), PaymentCommand("CASH", "93.00")],
            customer_id=service_context.customer.id,
        )
    )
    item = service_session.scalar(select(SaleItem).where(SaleItem.sale_id == sale.id))
    assert item is not None

    ReturnService(service_session).create_credit_note(
        CreateCreditNoteCommand(
            company_id=service_context.company.id,
            original_sale_id=sale.id,
            user_id=service_context.cashier.id,
            reason="CUSTOMER_REQUEST",
            on_date=date(2026, 9, 22),
            lines=[ReturnLineCommand(item.id, "1")],
        )
    )

    movements = tuple(
        service_session.scalars(
            select(LoyaltyLedger).where(LoyaltyLedger.sale_id == sale.id).order_by(LoyaltyLedger.id)
        )
    )
    assert [(movement.movement_type, movement.points) for movement in movements] == [
        ("REDEEM", Decimal("-100.000")),
        ("EARN", Decimal("11.800")),
        ("EARN_REVERSAL", Decimal("-11.800")),
        ("REDEEM_REVERSAL", Decimal("100.000")),
    ]
    customer = service_session.get(Customer, service_context.customer.id)
    assert customer is not None and customer.loyalty_points == Decimal("100.000")
