"""Gapless fiscal numbering integration tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import DocumentSeries, Sale
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.exceptions import InvoiceNumberError, ValidationError
from vglpos.services.inventory_service import InventoryService
from vglpos.services.invoice_number_service import InvoiceNumberService

from .conftest import ServiceContext


def _checkout_command(context: ServiceContext, attempt: int) -> CheckoutCommand:
    return CheckoutCommand(
        company_id=context.company.id,
        branch_id=context.branch.id,
        terminal_id=context.terminal.id,
        cashier_id=context.cashier.id,
        business_date=date(2026, 9, 17),
        offline_uuid=f"00000000-0000-4000-8000-{attempt:012d}",
        lines=[CheckoutLineCommand(context.product.id, Decimal("1.000"))],
        payments=[PaymentCommand("CASH", Decimal("118.00"))],
    )


def test_invoice_numbers_have_no_gaps(
    service_session: Session,
    service_context: ServiceContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = InventoryService.record_movement
    committed: list[int] = []

    for attempt in range(1, 101):
        if attempt % 10 == 0:

            def fail_after_numbering(*args: object, **kwargs: object) -> object:
                raise ValidationError("forced rollback after invoice allocation")

            monkeypatch.setattr(InventoryService, "record_movement", fail_after_numbering)
            with pytest.raises(ValidationError, match="forced rollback"):
                CheckoutService(service_session).checkout(
                    _checkout_command(service_context, attempt)
                )
            monkeypatch.setattr(InventoryService, "record_movement", original)
        else:
            sale = CheckoutService(service_session).checkout(
                _checkout_command(service_context, attempt)
            )
            committed.append(int(sale.invoice_number.removeprefix("S/")))

    assert committed == list(range(1, 91))
    assert tuple(service_session.scalars(select(Sale.invoice_number).order_by(Sale.id))) == tuple(
        f"S/{number:06d}" for number in range(1, 91)
    )


def test_invoice_number_rejects_more_than_sixteen_characters(
    service_session: Session, service_context: ServiceContext
) -> None:
    series = service_session.scalar(
        select(DocumentSeries).where(
            DocumentSeries.company_id == service_context.company.id,
            DocumentSeries.doc_type == "SALE",
        )
    )
    assert series is not None
    series.prefix = "PREFIX-TOO-LONG-"
    service_session.commit()

    with pytest.raises(InvoiceNumberError, match="16 characters"):
        InvoiceNumberService(service_session).allocate(
            service_context.company.id,
            service_context.branch.id,
            service_context.terminal.id,
            "SALE",
            date(2026, 9, 17),
        )
    service_session.rollback()
