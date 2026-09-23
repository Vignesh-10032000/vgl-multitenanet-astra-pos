"""Real two-session checkout contention regression tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from vglpos.domain.models import Product
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.exceptions import InsufficientStockError

from .conftest import open_service_shift, seed_service_context


def test_p0_7_concurrent_checkout_cannot_oversell(service_engine: Engine) -> None:
    with Session(service_engine, expire_on_commit=False) as seed_session:
        context = seed_service_context(seed_session, on_hand=Decimal("1.000"))
        shift = open_service_shift(seed_session, context)
        ids = (
            context.company.id,
            context.branch.id,
            context.terminal.id,
            context.cashier.id,
            context.product.id,
            shift.id,
        )
    barrier = Barrier(2)

    def attempt(index: int) -> str:
        company_id, branch_id, terminal_id, cashier_id, product_id, shift_id = ids
        command = CheckoutCommand(
            company_id=company_id,
            branch_id=branch_id,
            terminal_id=terminal_id,
            cashier_id=cashier_id,
            shift_id=shift_id,
            business_date=date(2026, 9, 17),
            offline_uuid=f"10000000-0000-4000-8000-{index:012d}",
            lines=[CheckoutLineCommand(product_id, "1")],
            payments=[PaymentCommand("CASH", "118.00")],
        )
        barrier.wait()
        with Session(service_engine, expire_on_commit=False) as session:
            try:
                CheckoutService(session).checkout(command)
            except InsufficientStockError:
                return "insufficient"
            return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(attempt, (1, 2)))

    with Session(service_engine) as verification_session:
        on_hand = verification_session.scalar(select(Product.on_hand).where(Product.id == ids[4]))
    assert outcomes == ["insufficient", "success"]
    assert on_hand == Decimal("0.000")
