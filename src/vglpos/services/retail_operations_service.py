"""Server-owned held bills and terminal quick-key operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.models import (
    HeldBill,
    Product,
    Sale,
    SaleItem,
    Shift,
    Terminal,
    TerminalQuickKey,
)
from vglpos.security.audit import record_audit_event
from vglpos.services.checkout_service import CheckoutLineCommand, CheckoutService, QuoteCommand
from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError
from vglpos.utils.money import ZERO


@dataclass(frozen=True, slots=True)
class HoldBillCommand:
    """Carry a server-priced cart into the held-bill store."""

    company_id: int
    branch_id: int
    terminal_id: int
    cashier_id: int
    shift_id: int
    lines: tuple[CheckoutLineCommand, ...] | list[CheckoutLineCommand]
    customer_id: int | None = None
    order_discount: object = ZERO
    apply_round_off: bool = True
    label: str | None = None


@dataclass(frozen=True, slots=True)
class QuickKeyAssignment:
    """Map one physical number key to an active catalogue product."""

    key_number: int
    product_id: int


@dataclass(frozen=True, slots=True)
class ConfigureQuickKeysCommand:
    """Replace a terminal's pinned product-key assignments atomically."""

    company_id: int
    branch_id: int
    terminal_id: int
    user_id: int
    assignments: tuple[QuickKeyAssignment, ...] | list[QuickKeyAssignment]


@dataclass(frozen=True, slots=True)
class QuickKeyEntry:
    """Expose either a pinned assignment or a server-ranked top seller."""

    key_number: int
    product: Product
    is_pinned: bool


class RetailOperationsService:
    """Coordinate carts parked at a counter and its keyboard-first product grid."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def hold_bill(self, cmd: HoldBillCommand) -> HeldBill:
        """Persist an authoritative cart snapshot without reserving or changing stock."""
        self._require_open_shift(
            cmd.company_id,
            cmd.branch_id,
            cmd.terminal_id,
            cmd.shift_id,
            cashier_id=cmd.cashier_id,
        )
        label = cmd.label.strip() if cmd.label else None
        if label is not None and len(label) > 100:
            raise ValidationError("Held-bill label cannot exceed 100 characters.")
        quote = CheckoutService(self.session).quote(
            QuoteCommand(
                company_id=cmd.company_id,
                branch_id=cmd.branch_id,
                lines=cmd.lines,
                customer_id=cmd.customer_id,
                order_discount=cmd.order_discount,
                apply_round_off=cmd.apply_round_off,
            )
        )
        payload: dict[str, object] = {
            "lines": [
                {
                    "product_id": line.product_id,
                    "quantity": str(line.quantity),
                    "line_discount": str(line.line_discount),
                }
                for line in cmd.lines
            ],
            "customer_id": cmd.customer_id,
            "order_discount": str(cmd.order_discount),
            "apply_round_off": cmd.apply_round_off,
        }
        held = HeldBill(
            company_id=cmd.company_id,
            branch_id=cmd.branch_id,
            terminal_id=cmd.terminal_id,
            cashier_id=cmd.cashier_id,
            shift_id=cmd.shift_id,
            label=label,
            cart_payload=payload,
            item_count=len(cmd.lines),
            net_amount=quote.net_amount,
            status="HELD",
            created_by=cmd.cashier_id,
        )
        try:
            self.session.add(held)
            self.session.commit()
            self.session.refresh(held)
            return held
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("The bill could not be held against the current shift.") from exc

    def list_held_bills(
        self, company_id: int, branch_id: int, terminal_id: int
    ) -> tuple[HeldBill, ...]:
        """Return only unresolved bills belonging to the authenticated counter."""
        self._require_terminal(company_id, branch_id, terminal_id)
        return tuple(
            self.session.scalars(
                select(HeldBill)
                .where(
                    HeldBill.company_id == company_id,
                    HeldBill.branch_id == branch_id,
                    HeldBill.terminal_id == terminal_id,
                    HeldBill.status == "HELD",
                    HeldBill.deleted_at.is_(None),
                )
                .order_by(HeldBill.created_at, HeldBill.id)
            )
        )

    def recall_bill(
        self,
        *,
        company_id: int,
        branch_id: int,
        terminal_id: int,
        cashier_id: int,
        held_bill_id: int,
    ) -> HeldBill:
        """Resolve one held cart exactly once and return its immutable snapshot."""
        held = self._get_held_bill(
            company_id=company_id,
            branch_id=branch_id,
            terminal_id=terminal_id,
            held_bill_id=held_bill_id,
            for_update=True,
        )
        self._require_open_shift(
            company_id,
            branch_id,
            terminal_id,
            held.shift_id,
            cashier_id=None,
        )
        if held.status != "HELD":
            raise ConflictError("Held bill has already been resolved.")
        held.status = "RECALLED"
        held.updated_by = cashier_id
        held.row_version += 1
        self.session.commit()
        self.session.refresh(held)
        return held

    def discard_bill(
        self,
        *,
        company_id: int,
        branch_id: int,
        terminal_id: int,
        user_id: int,
        held_bill_id: int,
    ) -> HeldBill:
        """Resolve an unwanted parked cart while retaining its audit history."""
        held = self._get_held_bill(
            company_id=company_id,
            branch_id=branch_id,
            terminal_id=terminal_id,
            held_bill_id=held_bill_id,
            for_update=True,
        )
        if held.status != "HELD":
            raise ConflictError("Held bill has already been resolved.")
        held.status = "DISCARDED"
        held.updated_by = user_id
        held.row_version += 1
        self.session.commit()
        self.session.refresh(held)
        return held

    def list_quick_keys(
        self, company_id: int, branch_id: int, terminal_id: int
    ) -> tuple[QuickKeyEntry, ...]:
        """Fill unpinned number keys with top sellers without persisting suggestions."""
        self._require_terminal(company_id, branch_id, terminal_id)
        pinned_rows = self.session.execute(
            select(TerminalQuickKey, Product)
            .join(Product, Product.id == TerminalQuickKey.product_id)
            .where(
                TerminalQuickKey.company_id == company_id,
                TerminalQuickKey.terminal_id == terminal_id,
                TerminalQuickKey.is_pinned.is_(True),
                TerminalQuickKey.deleted_at.is_(None),
                Product.company_id == company_id,
                Product.is_active.is_(True),
                Product.deleted_at.is_(None),
            )
            .order_by(TerminalQuickKey.key_number)
        ).all()
        entries = [QuickKeyEntry(key.key_number, product, True) for key, product in pinned_rows]
        used_keys = {entry.key_number for entry in entries}
        used_products = {entry.product.id for entry in entries}
        available_keys = [number for number in range(1, 13) if number not in used_keys]
        if not available_keys:
            return tuple(entries)
        since = date.today() - timedelta(days=90)
        top_products = tuple(
            self.session.scalars(
                select(Product)
                .join(SaleItem, SaleItem.product_id == Product.id)
                .join(Sale, Sale.id == SaleItem.sale_id)
                .where(
                    Product.company_id == company_id,
                    Product.id.not_in(used_products),
                    Product.is_active.is_(True),
                    Product.deleted_at.is_(None),
                    Sale.company_id == company_id,
                    Sale.branch_id == branch_id,
                    Sale.terminal_id == terminal_id,
                    Sale.business_date >= since,
                    Sale.sale_status.in_(("COMPLETED", "PARTIALLY_RETURNED", "RETURNED")),
                    Sale.deleted_at.is_(None),
                    SaleItem.company_id == company_id,
                    SaleItem.deleted_at.is_(None),
                )
                .group_by(Product.id)
                .order_by(func.sum(SaleItem.quantity).desc(), Product.id)
                .limit(len(available_keys))
            )
        )
        entries.extend(
            QuickKeyEntry(key_number, product, False)
            for key_number, product in zip(available_keys, top_products, strict=False)
        )
        return tuple(sorted(entries, key=lambda entry: entry.key_number))

    def configure_quick_keys(self, cmd: ConfigureQuickKeysCommand) -> tuple[QuickKeyEntry, ...]:
        """Replace pinned key assignments only after validating every product and key."""
        if not cmd.user_id:
            raise ValidationError("Authenticated user is required.")
        self._require_terminal(cmd.company_id, cmd.branch_id, cmd.terminal_id)
        assignments = tuple(cmd.assignments)
        numbers = [assignment.key_number for assignment in assignments]
        product_ids = [assignment.product_id for assignment in assignments]
        if len(assignments) > 12 or any(number < 1 or number > 12 for number in numbers):
            raise ValidationError("Quick keys must use unique numbers between 1 and 12.")
        if len(numbers) != len(set(numbers)) or len(product_ids) != len(set(product_ids)):
            raise ValidationError("Quick-key numbers and products must be unique.")
        products = {
            product.id
            for product in self.session.scalars(
                select(Product).where(
                    Product.company_id == cmd.company_id,
                    Product.id.in_(product_ids),
                    Product.is_active.is_(True),
                    Product.deleted_at.is_(None),
                )
            )
        }
        if products != set(product_ids):
            raise EntityNotFoundError("A quick-key product was not found.")
        existing = tuple(
            self.session.scalars(
                select(TerminalQuickKey).where(
                    TerminalQuickKey.company_id == cmd.company_id,
                    TerminalQuickKey.terminal_id == cmd.terminal_id,
                    TerminalQuickKey.deleted_at.is_(None),
                )
            )
        )
        try:
            for quick_key in existing:
                self.session.delete(quick_key)
            self.session.flush()
            self.session.add_all(
                TerminalQuickKey(
                    company_id=cmd.company_id,
                    terminal_id=cmd.terminal_id,
                    product_id=assignment.product_id,
                    key_number=assignment.key_number,
                    is_pinned=True,
                    created_by=cmd.user_id,
                )
                for assignment in assignments
            )
            record_audit_event(
                self.session,
                company_id=cmd.company_id,
                user_id=cmd.user_id,
                action="QUICK_KEYS_CONFIGURED",
                entity_type="Terminal",
                entity_id=cmd.terminal_id,
                new_values={
                    "assignments": [
                        {
                            "key_number": assignment.key_number,
                            "product_id": assignment.product_id,
                        }
                        for assignment in assignments
                    ]
                },
            )
            self.session.commit()
            return self.list_quick_keys(cmd.company_id, cmd.branch_id, cmd.terminal_id)
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Quick-key assignments conflict with current state.") from exc

    def _get_held_bill(
        self,
        *,
        company_id: int,
        branch_id: int,
        terminal_id: int,
        held_bill_id: int,
        for_update: bool,
    ) -> HeldBill:
        statement = select(HeldBill).where(
            HeldBill.id == held_bill_id,
            HeldBill.company_id == company_id,
            HeldBill.branch_id == branch_id,
            HeldBill.terminal_id == terminal_id,
            HeldBill.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        held = self.session.scalar(statement)
        if held is None:
            raise EntityNotFoundError("Held bill was not found.")
        return held

    def _require_open_shift(
        self,
        company_id: int,
        branch_id: int,
        terminal_id: int,
        shift_id: int,
        *,
        cashier_id: int | None,
    ) -> Shift:
        statement = select(Shift).where(
            Shift.id == shift_id,
            Shift.company_id == company_id,
            Shift.branch_id == branch_id,
            Shift.terminal_id == terminal_id,
            Shift.status == "OPEN",
            Shift.deleted_at.is_(None),
        )
        if cashier_id is not None:
            statement = statement.where(Shift.cashier_id == cashier_id)
        shift = self.session.scalar(statement)
        if shift is None:
            raise ConflictError("An open shift is required for held bills.")
        return shift

    def _require_terminal(self, company_id: int, branch_id: int, terminal_id: int) -> None:
        terminal = self.session.scalar(
            select(Terminal.id).where(
                Terminal.id == terminal_id,
                Terminal.company_id == company_id,
                Terminal.branch_id == branch_id,
                Terminal.is_active.is_(True),
                Terminal.deleted_at.is_(None),
            )
        )
        if terminal is None:
            raise EntityNotFoundError("Terminal was not found.")
