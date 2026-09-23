"""Customer counter reconciliation against completed fiscal sales."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from vglpos.domain.models import Customer
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.customer_reconciliation import CustomerCounterReconciliationService

from .conftest import ServiceContext, open_service_shift


def test_customer_counter_reconciliation_reports_and_repairs_drift(
    service_session: Session,
    service_context: ServiceContext,
) -> None:
    open_service_shift(service_session, service_context)
    CheckoutService(service_session).checkout(
        CheckoutCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            customer_id=service_context.customer.id,
            business_date=date(2026, 9, 19),
            lines=[CheckoutLineCommand(service_context.product.id, "1")],
            payments=[PaymentCommand("CASH", "118.00")],
        )
    )
    customer = service_session.get(Customer, service_context.customer.id)
    assert customer is not None
    customer.total_spent = Decimal("1.00")
    customer.total_orders = 9
    service_session.commit()

    service = CustomerCounterReconciliationService(service_session, service_context.company.id)
    reported = service.reconcile(apply=False)
    assert len(reported) == 1
    assert reported[0].expected_total_spent == Decimal("118.00")
    assert reported[0].expected_total_orders == 1
    service_session.refresh(customer)
    assert customer.total_spent == Decimal("1.00")
    assert customer.total_orders == 9

    repaired = service.reconcile(apply=True)
    assert len(repaired) == 1
    service_session.refresh(customer)
    assert customer.total_spent == Decimal("118.00")
    assert customer.total_orders == 1
