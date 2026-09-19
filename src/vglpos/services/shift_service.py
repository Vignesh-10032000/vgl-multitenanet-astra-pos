"""Cash-drawer shift lifecycle and Z-report calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.models import CashMovement, Sale, SalePayment, Shift, Terminal, User
from vglpos.security.audit import record_audit_event
from vglpos.services.exceptions import (
    EntityNotFoundError,
    ServiceError,
    ShiftError,
    ValidationError,
)
from vglpos.utils.money import ZERO, money


@dataclass(frozen=True, slots=True)
class OpenShiftCommand:
    """Carry authenticated shift-opening facts."""

    company_id: int
    branch_id: int
    terminal_id: int
    cashier_id: int
    opening_cash: object
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CloseShiftCommand:
    """Carry a blind drawer count without exposing the expected balance first."""

    company_id: int
    shift_id: int
    counted_cash: object
    user_id: int
    notes: str | None = None
    branch_id: int | None = None
    terminal_id: int | None = None


@dataclass(frozen=True, slots=True)
class CashMovementCommand:
    """Carry one reasoned pay-in, pay-out, float, or drop."""

    company_id: int
    shift_id: int
    movement_type: str
    amount: object
    reason: str
    user_id: int
    branch_id: int | None = None
    terminal_id: int | None = None


@dataclass(frozen=True, slots=True)
class ZReport:
    """Summarize one closed or open shift without mutating it."""

    shift_id: int
    gross_sales: Decimal
    net_sales: Decimal
    transaction_count: int
    cash_sales: Decimal
    cash_movements: Decimal
    expected_cash: Decimal
    counted_cash: Decimal | None
    variance: Decimal | None


class ShiftService:
    """Own drawer lifecycle mutations and their transaction boundaries."""

    _POSITIVE_MOVEMENTS = frozenset({"PAY_IN", "FLOAT", "CASH_IN"})
    _NEGATIVE_MOVEMENTS = frozenset({"PAY_OUT", "DROP", "CASH_OUT"})

    def __init__(self, session: Session) -> None:
        self.session = session

    def open_shift(self, cmd: OpenShiftCommand) -> Shift:
        """Create one open shift and commit only after uniqueness checks succeed."""
        try:
            opening_cash = money(cmd.opening_cash)
        except ValueError as exc:
            raise ValidationError("Opening cash must be numeric.") from exc
        if opening_cash < ZERO:
            raise ValidationError("Opening cash cannot be negative.")
        self._validate_actor_and_terminal(cmd)
        existing = self.session.scalar(
            select(Shift.id).where(
                Shift.company_id == cmd.company_id,
                Shift.terminal_id == cmd.terminal_id,
                Shift.status == "OPEN",
                Shift.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise ShiftError("The terminal already has an open shift.")
        shift = Shift(
            company_id=cmd.company_id,
            branch_id=cmd.branch_id,
            terminal_id=cmd.terminal_id,
            cashier_id=cmd.cashier_id,
            opening_cash=opening_cash,
            status="OPEN",
            notes=cmd.notes,
            created_by=cmd.cashier_id,
        )
        try:
            self.session.add(shift)
            self.session.commit()
            self.session.refresh(shift)
            return shift
        except IntegrityError as exc:
            self.session.rollback()
            raise ShiftError("The shift conflicted with another terminal operation.") from exc

    def close_shift(self, cmd: CloseShiftCommand) -> Shift:
        """Lock, settle, and commit a shift only after receiving the blind count."""
        try:
            counted = money(cmd.counted_cash)
        except ValueError as exc:
            raise ValidationError("Counted cash must be numeric.") from exc
        if counted < ZERO:
            raise ValidationError("Counted cash cannot be negative.")
        try:
            self._require_user(cmd.company_id, cmd.user_id)
            shift = self._open_shift(
                cmd.company_id,
                cmd.shift_id,
                branch_id=cmd.branch_id,
                terminal_id=cmd.terminal_id,
            )
            report = self._z_report(shift)
            shift.closing_cash_expected = report.expected_cash
            shift.closing_cash_counted = counted
            shift.cash_difference = money(counted - report.expected_cash)
            shift.closed_at = datetime.now(UTC)
            shift.status = "CLOSED"
            shift.notes = cmd.notes if cmd.notes is not None else shift.notes
            shift.updated_by = cmd.user_id
            shift.row_version += 1
            if shift.cash_difference != ZERO:
                record_audit_event(
                    self.session,
                    company_id=cmd.company_id,
                    user_id=cmd.user_id,
                    action="SHIFT_CLOSE_VARIANCE",
                    entity_type="Shift",
                    entity_id=shift.id,
                    new_values={
                        "expected_cash": str(shift.closing_cash_expected),
                        "counted_cash": str(shift.closing_cash_counted),
                        "variance": str(shift.cash_difference),
                    },
                )
            self.session.commit()
            self.session.refresh(shift)
            return shift
        except ServiceError:
            self.session.rollback()
            raise
        except IntegrityError as exc:
            self.session.rollback()
            raise ShiftError("The shift conflicted with another terminal operation.") from exc

    def record_cash_movement(self, cmd: CashMovementCommand) -> CashMovement:
        """Append a reasoned movement and commit it only while the shift remains open."""
        movement_type = cmd.movement_type.upper()
        allowed = self._POSITIVE_MOVEMENTS | self._NEGATIVE_MOVEMENTS
        if movement_type not in allowed:
            raise ValidationError(f"Unsupported cash movement type: {cmd.movement_type}.")
        if not cmd.reason.strip():
            raise ValidationError("A cash movement reason is required.")
        try:
            amount = money(cmd.amount)
        except ValueError as exc:
            raise ValidationError("Cash movement amount must be numeric.") from exc
        if amount <= ZERO:
            raise ValidationError("Cash movement amount must be greater than zero.")
        try:
            self._require_user(cmd.company_id, cmd.user_id)
            self._open_shift(
                cmd.company_id,
                cmd.shift_id,
                branch_id=cmd.branch_id,
                terminal_id=cmd.terminal_id,
            )
            movement = CashMovement(
                company_id=cmd.company_id,
                shift_id=cmd.shift_id,
                movement_type=movement_type,
                amount=amount,
                reason=cmd.reason.strip(),
                created_by=cmd.user_id,
            )
            self.session.add(movement)
            self.session.commit()
            self.session.refresh(movement)
            return movement
        except ServiceError:
            self.session.rollback()
            raise
        except IntegrityError as exc:
            self.session.rollback()
            raise ShiftError("The cash movement conflicted with shift state.") from exc

    def z_report(self, company_id: int, shift_id: int) -> ZReport:
        """Read one transactionally consistent shift summary without committing."""
        shift = self.session.scalar(
            select(Shift).where(
                Shift.id == shift_id,
                Shift.company_id == company_id,
                Shift.deleted_at.is_(None),
            )
        )
        if shift is None:
            raise EntityNotFoundError("Shift was not found.")
        return self._z_report(shift)

    def _open_shift(
        self,
        company_id: int,
        shift_id: int,
        *,
        branch_id: int | None = None,
        terminal_id: int | None = None,
    ) -> Shift:
        statement = select(Shift).where(
            Shift.id == shift_id,
            Shift.company_id == company_id,
            Shift.deleted_at.is_(None),
        )
        if branch_id is not None:
            statement = statement.where(Shift.branch_id == branch_id)
        if terminal_id is not None:
            statement = statement.where(Shift.terminal_id == terminal_id)
        shift = self.session.scalar(statement.with_for_update())
        if shift is None:
            raise EntityNotFoundError("Shift was not found.")
        if shift.status != "OPEN":
            raise ShiftError("Shift is not open.")
        return shift

    def _z_report(self, shift: Shift) -> ZReport:
        sale_row = self.session.execute(
            select(
                func.coalesce(func.sum(Sale.gross_amount), ZERO),
                func.coalesce(func.sum(Sale.net_amount), ZERO),
                func.count(Sale.id),
                func.coalesce(func.sum(Sale.amount_paid - Sale.net_amount), ZERO),
            ).where(
                Sale.company_id == shift.company_id,
                Sale.shift_id == shift.id,
                Sale.sale_status == "COMPLETED",
                Sale.deleted_at.is_(None),
            )
        ).one()
        gross, net, count, change = sale_row
        cash_tendered = self.session.scalar(
            select(func.coalesce(func.sum(SalePayment.amount), ZERO))
            .join(Sale, Sale.id == SalePayment.sale_id)
            .where(
                Sale.company_id == shift.company_id,
                Sale.shift_id == shift.id,
                Sale.sale_status == "COMPLETED",
                Sale.deleted_at.is_(None),
                SalePayment.company_id == shift.company_id,
                SalePayment.payment_method == "CASH",
                SalePayment.deleted_at.is_(None),
            )
        )
        movement_total = self.session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                CashMovement.movement_type.in_(self._POSITIVE_MOVEMENTS),
                                CashMovement.amount,
                            ),
                            else_=-CashMovement.amount,
                        )
                    ),
                    ZERO,
                )
            ).where(
                CashMovement.company_id == shift.company_id,
                CashMovement.shift_id == shift.id,
                CashMovement.deleted_at.is_(None),
            )
        )
        cash_sales = money((cash_tendered or ZERO) - change)
        signed_movements = money(movement_total or ZERO)
        expected = money(shift.opening_cash + cash_sales + signed_movements)
        return ZReport(
            shift_id=shift.id,
            gross_sales=money(gross),
            net_sales=money(net),
            transaction_count=int(count),
            cash_sales=cash_sales,
            cash_movements=signed_movements,
            expected_cash=expected,
            counted_cash=(
                money(shift.closing_cash_counted)
                if shift.closing_cash_counted is not None
                else None
            ),
            variance=money(shift.cash_difference) if shift.cash_difference is not None else None,
        )

    def _validate_actor_and_terminal(self, cmd: OpenShiftCommand) -> None:
        terminal = self.session.scalar(
            select(Terminal.id).where(
                Terminal.id == cmd.terminal_id,
                Terminal.company_id == cmd.company_id,
                Terminal.branch_id == cmd.branch_id,
                Terminal.deleted_at.is_(None),
                Terminal.is_active.is_(True),
            )
        )
        cashier = self.session.scalar(
            select(User.id).where(
                User.id == cmd.cashier_id,
                User.company_id == cmd.company_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        if terminal is None or cashier is None:
            raise EntityNotFoundError("Terminal or cashier was not found.")

    def _require_user(self, company_id: int, user_id: int) -> None:
        user = self.session.scalar(
            select(User.id).where(
                User.id == user_id,
                User.company_id == company_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise EntityNotFoundError("Shift user was not found.")
