"""Checkout transaction and validation integration tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vglpos.domain.models import Customer, Product, SaleItem, StockLedger
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.exceptions import InsufficientStockError, InvalidPaymentError

from .conftest import ServiceContext

ON_DATE = date(2026, 9, 17)


def _command(
    context: ServiceContext,
    *,
    lines: list[CheckoutLineCommand] | None = None,
    payments: list[PaymentCommand] | None = None,
    offline_uuid: str | None = None,
    customer_id: int | None = None,
) -> CheckoutCommand:
    return CheckoutCommand(
        company_id=context.company.id,
        branch_id=context.branch.id,
        terminal_id=context.terminal.id,
        cashier_id=context.cashier.id,
        customer_id=customer_id,
        offline_uuid=offline_uuid,
        business_date=ON_DATE,
        lines=lines or [CheckoutLineCommand(context.product.id, "1")],
        payments=payments or [PaymentCommand("CASH", "118.00")],
        client_total=Decimal("0.01"),
    )


def test_checkout_uses_server_price_and_updates_every_aggregate(
    service_session: Session, service_context: ServiceContext
) -> None:
    command = _command(
        service_context,
        lines=[
            CheckoutLineCommand(
                service_context.product.id,
                "1",
                client_unit_price="0.01",
                client_tax_rate="0",
            )
        ],
        customer_id=service_context.customer.id,
    )

    sale = CheckoutService(service_session).checkout(command)
    item = service_session.scalar(select(SaleItem).where(SaleItem.sale_id == sale.id))
    service_session.refresh(service_context.product)
    customer = service_session.get(Customer, service_context.customer.id)

    assert sale.net_amount == Decimal("118.00")
    assert item is not None and item.unit_price == Decimal("100.00")
    assert service_context.product.on_hand == Decimal("999.000")
    assert customer is not None
    assert customer.loyalty_points == Decimal("11.800")
    assert customer.total_spent == Decimal("118.00")
    assert customer.total_orders == 1
    assert (
        service_session.scalar(
            select(func.count())
            .select_from(StockLedger)
            .where(StockLedger.reference_id == str(sale.id))
        )
        == 1
    )


def test_duplicate_lines_are_aggregated_before_stock_check(
    service_session: Session, service_context: ServiceContext
) -> None:
    service_context.product.on_hand = Decimal("1.000")
    service_session.commit()
    command = _command(
        service_context,
        lines=[
            CheckoutLineCommand(service_context.product.id, "0.600"),
            CheckoutLineCommand(service_context.product.id, "0.600"),
        ],
        payments=[PaymentCommand("CASH", "142.00")],
    )

    with pytest.raises(InsufficientStockError):
        CheckoutService(service_session).checkout(command)
    assert service_session.get(Product, service_context.product.id).on_hand == Decimal("1.000")


def test_idempotent_replay_returns_original_sale(
    service_session: Session, service_context: ServiceContext
) -> None:
    command = _command(service_context, offline_uuid="6b76ec52-315c-47c4-a214-1f28b96daf23")
    service = CheckoutService(service_session)

    original = service.checkout(command)
    replay = service.checkout(command)

    assert replay.id == original.id
    assert service_session.scalar(select(func.count()).select_from(StockLedger)) == 1
    assert service_session.get(Product, service_context.product.id).on_hand == Decimal("999.000")


def test_customer_gstin_controls_interstate_tax(
    service_session: Session, service_context: ServiceContext
) -> None:
    service_context.customer.gstin = "29AACCR7832C1ZD"
    service_session.commit()

    sale = CheckoutService(service_session).checkout(
        _command(service_context, customer_id=service_context.customer.id)
    )

    assert sale.supply_type == "INTERSTATE"
    assert sale.igst_amount == Decimal("18.00")
    assert sale.cgst_amount == sale.sgst_amount == Decimal("0.00")


def test_change_must_be_covered_by_cash_tender(
    service_session: Session, service_context: ServiceContext
) -> None:
    command = _command(
        service_context,
        payments=[PaymentCommand("CARD", "120.00")],
    )

    with pytest.raises(InvalidPaymentError, match="non-cash"):
        CheckoutService(service_session).checkout(command)
