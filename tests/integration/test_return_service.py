"""Cumulative quantity and original-rate return integration tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import Product, SaleItem
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.exceptions import ReturnQuantityError
from vglpos.services.return_service import (
    CreateCreditNoteCommand,
    ReturnLineCommand,
    ReturnService,
)

from .conftest import ServiceContext, open_service_shift


def test_return_uses_original_invoice_tax_rate(
    service_session: Session, service_context: ServiceContext
) -> None:
    open_service_shift(service_session, service_context)
    sale = CheckoutService(service_session).checkout(
        CheckoutCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            customer_id=service_context.customer.id,
            business_date=date(2026, 9, 17),
            lines=[CheckoutLineCommand(service_context.product.id, "2")],
            payments=[PaymentCommand("CASH", "236.00")],
        )
    )
    item = service_session.scalar(select(SaleItem).where(SaleItem.sale_id == sale.id))
    assert item is not None
    service_context.tax_rate.rate = Decimal("5.00")
    service_context.tax_rate.cgst_rate = Decimal("2.50")
    service_context.tax_rate.sgst_rate = Decimal("2.50")
    service_context.tax_rate.igst_rate = Decimal("5.00")
    service_session.commit()

    note = ReturnService(service_session).create_credit_note(
        CreateCreditNoteCommand(
            company_id=service_context.company.id,
            original_sale_id=sale.id,
            user_id=service_context.cashier.id,
            reason="CUSTOMER_REQUEST",
            on_date=date(2026, 9, 17),
            lines=[ReturnLineCommand(item.id, "1")],
        )
    )

    assert note.net_amount == Decimal("118.00")
    assert sale.sale_status == "PARTIALLY_RETURNED"
    assert service_session.get(Product, service_context.product.id).on_hand == Decimal("999.000")


def test_return_validates_against_all_prior_credit_notes(
    service_session: Session, service_context: ServiceContext
) -> None:
    open_service_shift(service_session, service_context)
    sale = CheckoutService(service_session).checkout(
        CheckoutCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            business_date=date(2026, 9, 17),
            lines=[CheckoutLineCommand(service_context.product.id, "1")],
            payments=[PaymentCommand("CASH", "118.00")],
        )
    )
    item = service_session.scalar(select(SaleItem).where(SaleItem.sale_id == sale.id))
    assert item is not None
    service = ReturnService(service_session)
    command = CreateCreditNoteCommand(
        company_id=service_context.company.id,
        original_sale_id=sale.id,
        user_id=service_context.cashier.id,
        reason="DEFECTIVE",
        on_date=date(2026, 9, 17),
        lines=[ReturnLineCommand(item.id, "0.600")],
    )
    service.create_credit_note(command)

    with pytest.raises(ReturnQuantityError):
        service.create_credit_note(command)
