"""Shift settlement and set-based report integration tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import AuditLog
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.report_service import ReportService
from vglpos.services.shift_service import (
    CashMovementCommand,
    CloseShiftCommand,
    OpenShiftCommand,
    ShiftService,
)

from .conftest import ServiceContext, open_service_shift


def test_shift_blind_count_records_exact_variance(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = ShiftService(service_session)
    shift = service.open_shift(
        OpenShiftCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            opening_cash="200.00",
            denomination_counts={"200": 1},
        )
    )
    CheckoutService(service_session).checkout(
        CheckoutCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            shift_id=shift.id,
            business_date=date(2026, 9, 17),
            lines=[CheckoutLineCommand(service_context.product.id, "1")],
            payments=[PaymentCommand("CASH", "120.00")],
        )
    )
    service.record_cash_movement(
        CashMovementCommand(
            company_id=service_context.company.id,
            shift_id=shift.id,
            movement_type="PAY_OUT",
            amount="20.00",
            reason="Petty cash",
            user_id=service_context.cashier.id,
        )
    )

    before_close = service.z_report(service_context.company.id, shift.id)
    closed = service.close_shift(
        CloseShiftCommand(
            company_id=service_context.company.id,
            shift_id=shift.id,
            counted_cash="290.00",
            denomination_counts={"200": 1, "50": 1, "20": 2},
            user_id=service_context.cashier.id,
            notes="Eight rupees short",
        )
    )

    assert before_close.cash_sales == Decimal("118.00")
    assert before_close.expected_cash == Decimal("298.00")
    assert closed.closing_cash_expected == Decimal("298.00")
    assert closed.cash_difference == Decimal("-8.00")
    variance = service_session.scalar(
        select(AuditLog).where(
            AuditLog.company_id == service_context.company.id,
            AuditLog.action == "SHIFT_CLOSE_VARIANCE",
        )
    )
    assert variance is not None
    assert variance.user_id == service_context.cashier.id
    assert variance.new_values is not None
    assert variance.new_values["variance"] == "-8.00"


def test_report_service_groups_sales_without_query_loops(
    service_session: Session, service_context: ServiceContext
) -> None:
    open_service_shift(service_session, service_context)
    on_date = date(2026, 9, 17)
    CheckoutService(service_session).checkout(
        CheckoutCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            business_date=on_date,
            lines=[CheckoutLineCommand(service_context.product.id, "2")],
            payments=[PaymentCommand("UPI", "236.00", "UPI-REF")],
        )
    )
    reports = ReportService(service_session, service_context.company.id)

    summary = reports.daily_summary(on_date)
    revenue = reports.revenue_series(on_date, on_date)
    products = reports.top_products(on_date, on_date)
    payments = reports.payment_mix(on_date, on_date)
    gstr1 = reports.gstr1_data(on_date, on_date)

    assert summary.total_bills == 1
    assert summary.net_amount == Decimal("236.00")
    assert revenue[0].net_amount == Decimal("236.00")
    assert products[0].quantity == Decimal("2.000")
    assert payments[0].payment_method == "UPI"
    assert payments[0].amount == Decimal("236.00")
    assert gstr1[0].table == "7"
    assert gstr1[0].taxable_amount == Decimal("200.00")

    reports.record_export(
        user_id=service_context.cashier.id,
        report_name="GSTR-1",
        start_date=on_date,
        end_date=on_date,
        output_format="csv",
    )
    export = service_session.scalar(
        select(AuditLog).where(
            AuditLog.company_id == service_context.company.id,
            AuditLog.action == "EXPORT",
        )
    )
    assert export is not None
    assert export.entity_id == "GSTR-1"
    assert export.new_values is not None
    assert export.new_values["format"] == "CSV"


def test_z_report_does_not_duplicate_split_tender_sale_totals(
    service_session: Session, service_context: ServiceContext
) -> None:
    shift_service = ShiftService(service_session)
    shift = shift_service.open_shift(
        OpenShiftCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            opening_cash="100.00",
            denomination_counts={"100": 1},
        )
    )
    CheckoutService(service_session).checkout(
        CheckoutCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            shift_id=shift.id,
            business_date=date(2026, 9, 17),
            lines=[CheckoutLineCommand(service_context.product.id, "1")],
            payments=[
                PaymentCommand("CARD", "100.00", "CARD-REF"),
                PaymentCommand("CASH", "20.00"),
            ],
        )
    )

    report = shift_service.z_report(service_context.company.id, shift.id)

    assert report.transaction_count == 1
    assert report.gross_sales == Decimal("100.00")
    assert report.net_sales == Decimal("118.00")
    assert report.cash_sales == Decimal("18.00")
    assert report.expected_cash == Decimal("118.00")
