"""Phase 7 drawer lifecycle, denomination, approval, and Z-report tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import (
    AuditLog,
    Permission,
    Role,
    RolePermission,
    SaleItem,
    UserRole,
)
from vglpos.security.password import hash_pin
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.exceptions import AuthorizationError, ShiftError, ValidationError
from vglpos.services.return_service import (
    CreateCreditNoteCommand,
    ReturnLineCommand,
    ReturnService,
)
from vglpos.services.shift_service import (
    CashMovementCommand,
    CloseShiftCommand,
    DrawerOpenCommand,
    OpenShiftCommand,
    ShiftService,
)

from .conftest import ServiceContext


def _open_command(context: ServiceContext, opening_cash: str = "100.00") -> OpenShiftCommand:
    return OpenShiftCommand(
        company_id=context.company.id,
        branch_id=context.branch.id,
        terminal_id=context.terminal.id,
        cashier_id=context.cashier.id,
        opening_cash=opening_cash,
        denomination_counts={"100": 1} if opening_cash == "100.00" else {},
    )


def _grant_shift_manager(session: Session, context: ServiceContext) -> None:
    permission = Permission(
        code="shift.close",
        description="Close and reconcile a shift",
        category="shift",
    )
    role = Role(
        company_id=context.company.id,
        name="MANAGER",
        description="Shift approver",
        is_system=True,
    )
    context.cashier.pin_hash = hash_pin("2468")
    session.add_all([permission, role])
    session.flush()
    session.add_all(
        [
            RolePermission(
                company_id=context.company.id,
                role_id=role.id,
                permission_id=permission.id,
            ),
            UserRole(
                company_id=context.company.id,
                user_id=context.cashier.id,
                role_id=role.id,
                branch_id=None,
            ),
        ]
    )
    session.commit()


def test_denomination_totals_must_match_declared_cash(
    service_session: Session, service_context: ServiceContext
) -> None:
    with pytest.raises(ValidationError, match="does not match"):
        ShiftService(service_session).open_shift(
            OpenShiftCommand(
                company_id=service_context.company.id,
                branch_id=service_context.branch.id,
                terminal_id=service_context.terminal.id,
                cashier_id=service_context.cashier.id,
                opening_cash="200.00",
                denomination_counts={"100": 1},
            )
        )

    with pytest.raises(ValidationError, match="counts are required"):
        ShiftService(service_session).open_shift(
            OpenShiftCommand(
                company_id=service_context.company.id,
                branch_id=service_context.branch.id,
                terminal_id=service_context.terminal.id,
                cashier_id=service_context.cashier.id,
                opening_cash="100.00",
                denomination_counts={},
            )
        )


def test_unique_open_shift_per_terminal(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = ShiftService(service_session)
    service.open_shift(_open_command(service_context))

    with pytest.raises(ShiftError, match="already has an open shift"):
        service.open_shift(_open_command(service_context))


def test_large_variance_requires_manager_pin_and_reason(
    service_session: Session, service_context: ServiceContext
) -> None:
    _grant_shift_manager(service_session, service_context)
    service = ShiftService(service_session)
    shift = service.open_shift(_open_command(service_context))
    command = CloseShiftCommand(
        company_id=service_context.company.id,
        shift_id=shift.id,
        counted_cash="0.00",
        denomination_counts={},
        user_id=service_context.cashier.id,
    )

    with pytest.raises(AuthorizationError, match="Manager PIN"):
        service.close_shift(command)

    closed = service.close_shift(
        CloseShiftCommand(
            company_id=service_context.company.id,
            shift_id=shift.id,
            counted_cash="0.00",
            denomination_counts={},
            user_id=service_context.cashier.id,
            approver_user_id=service_context.cashier.id,
            approval_pin="2468",
            variance_reason="Verified opening-float shortage",
        )
    )

    assert closed.cash_difference == Decimal("-100.00")
    assert closed.variance_approved_by == service_context.cashier.id
    assert closed.variance_reason == "Verified opening-float shortage"
    approval = service_session.scalar(
        select(AuditLog).where(AuditLog.action == "SHIFT_VARIANCE_APPROVAL")
    )
    assert approval is not None


def test_complete_z_report_includes_tenders_returns_tax_movements_and_no_sales(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = ShiftService(service_session)
    shift = service.open_shift(_open_command(service_context))
    sale = CheckoutService(service_session).checkout(
        CheckoutCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            customer_id=service_context.customer.id,
            shift_id=shift.id,
            business_date=date(2026, 9, 22),
            lines=[CheckoutLineCommand(service_context.product.id, "1")],
            payments=[
                PaymentCommand("CARD", "100.00", "CARD-Z-001"),
                PaymentCommand("CASH", "20.00"),
            ],
        )
    )
    item = service_session.scalar(select(SaleItem).where(SaleItem.sale_id == sale.id))
    assert item is not None
    ReturnService(service_session).create_credit_note(
        CreateCreditNoteCommand(
            company_id=service_context.company.id,
            original_sale_id=sale.id,
            user_id=service_context.cashier.id,
            reason="CUSTOMER_REQUEST",
            on_date=date(2026, 9, 22),
            lines=[ReturnLineCommand(item.id, "0.500")],
        )
    )
    service.record_cash_movement(
        CashMovementCommand(
            company_id=service_context.company.id,
            shift_id=shift.id,
            movement_type="PAY_IN",
            amount="25.00",
            reason="Additional change float",
            user_id=service_context.cashier.id,
        )
    )
    service.record_cash_movement(
        CashMovementCommand(
            company_id=service_context.company.id,
            shift_id=shift.id,
            movement_type="PAY_OUT",
            amount="5.00",
            reason="Courier charge",
            user_id=service_context.cashier.id,
        )
    )
    service.record_no_sale(
        DrawerOpenCommand(
            company_id=service_context.company.id,
            shift_id=shift.id,
            reason="Make change",
            user_id=service_context.cashier.id,
        )
    )

    report = service.z_report(service_context.company.id, shift.id)

    assert report.transaction_count == 1
    assert report.gross_sales == Decimal("100.00")
    assert report.net_sales == Decimal("118.00")
    assert report.payment_totals == {"CARD": Decimal("100.00"), "CASH": Decimal("20.00")}
    assert report.cash_sales == Decimal("18.00")
    assert report.cash_movements == Decimal("20.00")
    assert report.expected_cash == Decimal("138.00")
    assert report.return_count == 1
    assert report.return_total == Decimal("59.00")
    assert report.no_sale_count == 1
    assert report.cgst_amount == report.sgst_amount == Decimal("9.00")
