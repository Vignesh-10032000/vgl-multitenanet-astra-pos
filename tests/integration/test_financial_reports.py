"""Hand-calculated financial and management report integration tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import Category, SaleItem, Supplier, SupplierLedger
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.exceptions import ValidationError
from vglpos.services.financial_report_service import FinancialReportService
from vglpos.services.return_service import (
    CreateCreditNoteCommand,
    ReturnLineCommand,
    ReturnService,
)
from vglpos.services.shift_service import CashMovementCommand, ShiftService

from .conftest import ServiceContext, open_service_shift


def _seed_financial_fixture(
    session: Session, context: ServiceContext
) -> tuple[date, date, Supplier]:
    today = date.today()
    previous = today - timedelta(days=45)
    category = Category(
        company_id=context.company.id,
        code="GROCERY",
        name="Grocery",
    )
    supplier = Supplier(
        company_id=context.company.id,
        code="SUP-1",
        name="Primary Supplier",
        phone="8000000099",
        state_code="33",
        payment_terms_days=30,
        outstanding_balance=Decimal("400.00"),
    )
    session.add_all([category, supplier])
    session.flush()
    context.product.category_id = category.id
    context.product.brand = "Fixture Brand"
    context.product.preferred_supplier_id = supplier.id
    context.customer.credit_limit = Decimal("1000.00")
    session.commit()
    shift = open_service_shift(session, context)
    checkout = CheckoutService(session)
    previous_sale = checkout.checkout(
        CheckoutCommand(
            company_id=context.company.id,
            branch_id=context.branch.id,
            terminal_id=context.terminal.id,
            cashier_id=context.cashier.id,
            customer_id=context.customer.id,
            business_date=previous,
            lines=[CheckoutLineCommand(context.product.id, "1")],
            payments=[PaymentCommand("CREDIT", "118.00")],
        )
    )
    current_sale = checkout.checkout(
        CheckoutCommand(
            company_id=context.company.id,
            branch_id=context.branch.id,
            terminal_id=context.terminal.id,
            cashier_id=context.cashier.id,
            business_date=today,
            lines=[CheckoutLineCommand(context.product.id, "2")],
            payments=[PaymentCommand("CASH", "236.00")],
        )
    )
    item = session.scalar(select(SaleItem).where(SaleItem.sale_id == current_sale.id))
    assert item is not None
    ReturnService(session).create_credit_note(
        CreateCreditNoteCommand(
            company_id=context.company.id,
            original_sale_id=current_sale.id,
            user_id=context.cashier.id,
            reason="CUSTOMER_REQUEST",
            on_date=today,
            lines=[ReturnLineCommand(item.id, "0.500")],
        )
    )
    shifts = ShiftService(session)
    for movement_type, amount, reason in (
        ("PAY_IN", "20.00", "Petty cash reimbursement"),
        ("PAY_OUT", "5.00", "Courier"),
    ):
        shifts.record_cash_movement(
            CashMovementCommand(
                company_id=context.company.id,
                shift_id=shift.id,
                movement_type=movement_type,
                amount=amount,
                reason=reason,
                user_id=context.cashier.id,
                branch_id=context.branch.id,
                terminal_id=context.terminal.id,
            )
        )
    session.add_all(
        [
            SupplierLedger(
                company_id=context.company.id,
                supplier_id=supplier.id,
                txn_date=previous,
                txn_type="INVOICE",
                reference_type="purchases",
                reference_id="OLD",
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("300.00"),
                balance_after=Decimal("300.00"),
                due_date=previous,
                created_by=context.cashier.id,
            ),
            SupplierLedger(
                company_id=context.company.id,
                supplier_id=supplier.id,
                txn_date=today,
                txn_type="INVOICE",
                reference_type="purchases",
                reference_id="CURRENT",
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("200.00"),
                balance_after=Decimal("500.00"),
                due_date=today + timedelta(days=5),
                created_by=context.cashier.id,
            ),
            SupplierLedger(
                company_id=context.company.id,
                supplier_id=supplier.id,
                txn_date=today,
                txn_type="PAYMENT",
                reference_type="supplier_payment",
                reference_id="PAY-1",
                debit_amount=Decimal("100.00"),
                credit_amount=Decimal("0.00"),
                balance_after=Decimal("400.00"),
                created_by=context.cashier.id,
            ),
        ]
    )
    session.commit()
    assert previous_sale.id is not None
    return today, previous, supplier


def test_margin_day_cash_ageing_comparison_and_hourly_reports_are_hand_calculated(
    service_session: Session, service_context: ServiceContext
) -> None:
    today, previous, supplier = _seed_financial_fixture(service_session, service_context)
    service = FinancialReportService(service_session, service_context.company.id)

    for dimension, expected_key in (
        ("PRODUCT", service_context.product.sku),
        ("CATEGORY", str(service_context.product.category_id)),
        ("BRAND", "FIXTURE BRAND"),
        ("SUPPLIER", supplier.code),
    ):
        rows = service.gross_margin(today, today, dimension=dimension)
        assert len(rows) == 1
        assert rows[0].key == expected_key
        assert rows[0].quantity == Decimal("1.500")
        assert rows[0].net_sales == Decimal("150.00")
        assert rows[0].cost_of_goods == Decimal("90.00")
        assert rows[0].gross_margin == Decimal("60.00")
        assert rows[0].margin_percent == Decimal("40.00")

    day_book = service.day_book(today, today)
    assert [(row.document_type, row.debit_amount, row.credit_amount) for row in day_book] == [
        ("CREDIT_NOTE", Decimal("0.00"), Decimal("59.00")),
        ("SALE", Decimal("236.00"), Decimal("0.00")),
        ("SUPPLIER_PAYMENT", Decimal("100.00"), Decimal("0.00")),
    ]
    cash_book = service.cash_book(today, today)
    assert sum((row.cash_in for row in cash_book), Decimal("0.00")) == Decimal("256.00")
    assert sum((row.cash_out for row in cash_book), Decimal("0.00")) == Decimal("5.00")
    assert cash_book[-1].balance == Decimal("251.00")

    customer_ageing = service.customer_ageing(as_of=today)
    assert len(customer_ageing) == 1
    assert customer_ageing[0].days_31_60 == Decimal("118.00")
    assert customer_ageing[0].total == Decimal("118.00")
    supplier_ageing = service.supplier_ageing(as_of=today)
    assert len(supplier_ageing) == 1
    assert supplier_ageing[0].current == Decimal("200.00")
    assert supplier_ageing[0].days_31_60 == Decimal("200.00")
    assert supplier_ageing[0].total == Decimal("400.00")

    comparison = service.sales_comparison(today, today, previous, previous)
    assert comparison.current.quantity == Decimal("1.500")
    assert comparison.current.net_sales == Decimal("150.00")
    assert comparison.current.gross_margin == Decimal("60.00")
    assert comparison.previous.quantity == Decimal("1.000")
    assert comparison.previous.net_sales == Decimal("100.00")
    assert comparison.previous.gross_margin == Decimal("40.00")
    assert comparison.sales_change == Decimal("50.00")
    assert comparison.sales_change_percent == Decimal("50.00")
    assert comparison.margin_change == Decimal("20.00")

    hourly = service.hourly_sales(today, today)
    assert sum(row.bill_count for row in hourly) == 1
    assert sum((row.quantity for row in hourly), Decimal("0.000")) == Decimal("2.000")
    assert sum((row.net_sales for row in hourly), Decimal("0.00")) == Decimal("236.00")


def test_financial_reports_reject_reversed_dates(
    service_session: Session, service_context: ServiceContext
) -> None:
    with pytest.raises(ValidationError, match="start date"):
        FinancialReportService(service_session, service_context.company.id).day_book(
            date(2026, 9, 2), date(2026, 9, 1)
        )
