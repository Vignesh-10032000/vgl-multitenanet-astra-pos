"""Atomic stock balance and ledger integration tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import AuditLog, Product, StockLedger
from vglpos.services.exceptions import InsufficientStockError, ValidationError
from vglpos.services.inventory_service import InventoryService

from .conftest import ServiceContext


def test_record_movement_updates_balance_and_ledger_atomically(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = InventoryService(service_session, service_context.company.id)

    ledger = service.record_movement(
        service_context.product,
        service_context.branch.id,
        Decimal("-3.500"),
        "SALE",
        "sales",
        101,
        service_context.cashier.id,
    )
    service_session.commit()
    service_session.refresh(service_context.product)

    assert service_context.product.on_hand == Decimal("996.500")
    assert ledger.balance_after == Decimal("996.500")
    assert service_session.scalar(select(StockLedger).where(StockLedger.id == ledger.id)) == ledger


def test_atomic_stock_guard_prevents_negative_balance(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = InventoryService(service_session, service_context.company.id)

    with pytest.raises(InsufficientStockError):
        service.record_movement(
            service_context.product,
            service_context.branch.id,
            Decimal("-1000.001"),
            "SALE",
            "sales",
            102,
            service_context.cashier.id,
        )
    service_session.rollback()
    assert service_session.get(Product, service_context.product.id).on_hand == Decimal("1000.000")


def test_reserve_release_adjust_and_weighted_cost(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = InventoryService(service_session, service_context.company.id)

    assert service.reserve_stock(service_context.product, "10") == Decimal("10.000")
    assert service.release_reservation(service_context.product, "4") == Decimal("6.000")
    with pytest.raises(ValidationError, match="reason"):
        service.adjust_stock(
            service_context.product,
            service_context.branch.id,
            "1",
            " ",
            service_context.cashier.id,
        )
    assert service.weighted_average_cost_update(
        service_context.product, "1000", "80.00"
    ) == Decimal("70.00")
    service.adjust_stock(
        service_context.product,
        service_context.branch.id,
        "2",
        "Cycle count correction",
        service_context.cashier.id,
    )
    service_session.commit()
    service_session.refresh(service_context.product)
    assert service_context.product.reserved_quantity == Decimal("6.000")
    assert service_context.product.cost_price == Decimal("70.00")
    assert service_context.product.on_hand == Decimal("1002.000")
    adjustment = service_session.scalar(
        select(AuditLog).where(
            AuditLog.company_id == service_context.company.id,
            AuditLog.action == "STOCK_ADJUST",
        )
    )
    assert adjustment is not None
    assert adjustment.user_id == service_context.cashier.id
    assert adjustment.new_values is not None
    assert adjustment.new_values["reason"] == "Cycle count correction"
