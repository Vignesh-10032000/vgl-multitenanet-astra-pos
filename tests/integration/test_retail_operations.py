"""Server-side held bills and terminal quick-key integration tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from vglpos.domain.models import Product
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.exceptions import ShiftError
from vglpos.services.retail_operations_service import (
    ConfigureQuickKeysCommand,
    HoldBillCommand,
    QuickKeyAssignment,
    RetailOperationsService,
)
from vglpos.services.shift_service import CloseShiftCommand

from .conftest import ServiceContext, open_service_shift


def _hold_command(context: ServiceContext, shift_id: int) -> HoldBillCommand:
    return HoldBillCommand(
        company_id=context.company.id,
        branch_id=context.branch.id,
        terminal_id=context.terminal.id,
        cashier_id=context.cashier.id,
        shift_id=shift_id,
        label="Blue shirt customer",
        lines=[CheckoutLineCommand(context.product.id, "2")],
        customer_id=context.customer.id,
    )


def test_held_bill_lifecycle_never_reserves_stock(
    service_session: Session, service_context: ServiceContext
) -> None:
    shift = open_service_shift(service_session, service_context)
    service = RetailOperationsService(service_session)

    held = service.hold_bill(_hold_command(service_context, shift.id))

    service_session.refresh(service_context.product)
    assert held.item_count == 1
    assert held.net_amount == Decimal("236.00")
    assert service_context.product.on_hand == Decimal("1000.000")
    assert service_context.product.reserved_quantity == Decimal("0.000")
    assert [
        bill.id
        for bill in service.list_held_bills(
            service_context.company.id, service_context.branch.id, service_context.terminal.id
        )
    ] == [held.id]

    recalled = service.recall_bill(
        company_id=service_context.company.id,
        branch_id=service_context.branch.id,
        terminal_id=service_context.terminal.id,
        cashier_id=service_context.cashier.id,
        held_bill_id=held.id,
    )
    assert recalled.status == "RECALLED"
    assert recalled.cart_payload["lines"] == [
        {"product_id": service_context.product.id, "quantity": "2", "line_discount": "0.00"}
    ]


def test_shift_close_requires_confirmation_then_expires_held_bills(
    service_session: Session, service_context: ServiceContext
) -> None:
    shift = open_service_shift(service_session, service_context)
    held = RetailOperationsService(service_session).hold_bill(
        _hold_command(service_context, shift.id)
    )
    from vglpos.services.shift_service import ShiftService

    shift_service = ShiftService(service_session)
    command = CloseShiftCommand(
        company_id=service_context.company.id,
        shift_id=shift.id,
        counted_cash="0.00",
        denomination_counts={},
        user_id=service_context.cashier.id,
    )
    with pytest.raises(ShiftError, match="held bill"):
        shift_service.close_shift(command)

    closed = shift_service.close_shift(
        CloseShiftCommand(
            company_id=service_context.company.id,
            shift_id=shift.id,
            counted_cash="0.00",
            denomination_counts={},
            user_id=service_context.cashier.id,
            expire_held_bills=True,
        )
    )
    service_session.refresh(held)
    assert closed.status == "CLOSED"
    assert held.status == "EXPIRED"


def test_quick_keys_combine_pins_with_top_sellers(
    service_session: Session, service_context: ServiceContext
) -> None:
    shift = open_service_shift(service_session, service_context)
    pinned = Product(
        company_id=service_context.company.id,
        sku="PIN-002",
        name="Pinned product",
        tax_rate_id=service_context.tax_rate.id,
        cost_price=Decimal("10.00"),
        selling_price=Decimal("20.00"),
        mrp=Decimal("23.60"),
        on_hand=Decimal("50.000"),
    )
    service_session.add(pinned)
    service_session.commit()
    CheckoutService(service_session).checkout(
        CheckoutCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            shift_id=shift.id,
            business_date=date.today(),
            lines=[CheckoutLineCommand(service_context.product.id, "1")],
            payments=[PaymentCommand("CASH", "118.00")],
        )
    )
    service = RetailOperationsService(service_session)
    entries = service.configure_quick_keys(
        ConfigureQuickKeysCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            user_id=service_context.cashier.id,
            assignments=[QuickKeyAssignment(5, pinned.id)],
        )
    )

    assert [(entry.key_number, entry.product.id, entry.is_pinned) for entry in entries] == [
        (1, service_context.product.id, False),
        (5, pinned.id, True),
    ]
