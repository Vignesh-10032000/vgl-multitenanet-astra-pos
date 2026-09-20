"""Reconcile denormalized customer sale counters against fiscal documents."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vglpos.domain.models import Customer, Sale
from vglpos.utils.money import ZERO, money


@dataclass(frozen=True, slots=True)
class CustomerCounterDrift:
    customer_id: int
    stored_total_spent: Decimal
    expected_total_spent: Decimal
    stored_total_orders: int
    expected_total_orders: int


class CustomerCounterReconciliationService:
    """Compare and optionally repair customer counters for one tenant."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def reconcile(self, *, apply: bool) -> tuple[CustomerCounterDrift, ...]:
        """Return every drift and repair it in the same transaction when requested."""
        aggregate_rows = self.session.execute(
            select(
                Sale.customer_id,
                func.count(Sale.id),
                func.coalesce(func.sum(Sale.net_amount), ZERO),
            )
            .where(
                Sale.company_id == self.company_id,
                Sale.customer_id.is_not(None),
                Sale.sale_status == "COMPLETED",
                Sale.deleted_at.is_(None),
            )
            .group_by(Sale.customer_id)
        )
        expected = {
            int(row[0]): (int(row[1]), money(row[2]))
            for row in aggregate_rows
            if row[0] is not None
        }
        customers = self.session.scalars(
            select(Customer).where(
                Customer.company_id == self.company_id,
                Customer.deleted_at.is_(None),
            )
        )
        drift: list[CustomerCounterDrift] = []
        for customer in customers:
            expected_orders, expected_spent = expected.get(customer.id, (0, ZERO))
            stored_spent = money(customer.total_spent)
            if customer.total_orders == expected_orders and stored_spent == expected_spent:
                continue
            drift.append(
                CustomerCounterDrift(
                    customer_id=customer.id,
                    stored_total_spent=stored_spent,
                    expected_total_spent=expected_spent,
                    stored_total_orders=customer.total_orders,
                    expected_total_orders=expected_orders,
                )
            )
            if apply:
                customer.total_spent = expected_spent
                customer.total_orders = expected_orders
                customer.row_version += 1
        if apply:
            self.session.commit()
        return tuple(drift)
