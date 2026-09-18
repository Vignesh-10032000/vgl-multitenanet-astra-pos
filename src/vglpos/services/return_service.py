"""Credit-note creation against immutable original invoice snapshots."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.enums import DocType, ReturnReason, SaleStatus
from vglpos.domain.models import (
    CreditNote,
    CreditNoteItem,
    Customer,
    Product,
    Sale,
    SaleItem,
)
from vglpos.services.checkout_service import LOYALTY_EARN_DIVISOR
from vglpos.services.exceptions import (
    CheckoutError,
    EntityNotFoundError,
    ReturnQuantityError,
    ServiceError,
    ValidationError,
)
from vglpos.services.inventory_service import InventoryService
from vglpos.services.invoice_number_service import InvoiceNumberService
from vglpos.utils.money import ZERO, money, qty, to_decimal

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReturnLineCommand:
    """Request a quantity from one immutable original sale line."""

    sale_item_id: int
    quantity: object


@dataclass(frozen=True, slots=True)
class CreateCreditNoteCommand:
    """Carry authenticated return facts into the transactional service."""

    company_id: int
    original_sale_id: int
    user_id: int
    reason: str
    lines: tuple[ReturnLineCommand, ...] | list[ReturnLineCommand]
    on_date: date = field(default_factory=date.today)


class ReturnService:
    """Validate cumulative returns and persist a tax-faithful credit note."""

    def __init__(
        self,
        session: Session,
        *,
        loyalty_earn_divisor: Decimal = LOYALTY_EARN_DIVISOR,
    ) -> None:
        if loyalty_earn_divisor <= ZERO:
            raise ValueError("loyalty_earn_divisor must be positive.")
        self.session = session
        self.loyalty_earn_divisor = loyalty_earn_divisor

    def create_credit_note(self, cmd: CreateCreditNoteCommand) -> CreditNote:
        """Commit one credit note, stock reversal, and loyalty reversal atomically."""
        if not cmd.company_id or not cmd.user_id:
            raise ValidationError("Company and user are required for a return.")
        if not cmd.reason.strip():
            raise ValidationError("A return reason is required.")
        if cmd.reason.strip().upper() not in {reason.value for reason in ReturnReason}:
            raise ValidationError(f"Unsupported return reason: {cmd.reason}.")
        if not cmd.lines:
            raise ValidationError("At least one return line is required.")
        try:
            credit_note = self._create(cmd)
            self.session.commit()
            self.session.refresh(credit_note)
            return credit_note
        except IntegrityError as exc:
            self.session.rollback()
            logger.exception(
                "Credit note persistence conflict",
                extra={"company_id": cmd.company_id, "sale_id": cmd.original_sale_id},
            )
            raise CheckoutError("Credit note conflicted with another transaction.") from exc
        except ServiceError:
            self.session.rollback()
            raise
        except ValueError as exc:
            self.session.rollback()
            raise ValidationError(str(exc)) from exc

    def _create(self, cmd: CreateCreditNoteCommand) -> CreditNote:
        sale = self.session.scalar(
            select(Sale)
            .where(
                Sale.id == cmd.original_sale_id,
                Sale.company_id == cmd.company_id,
                Sale.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if sale is None:
            raise EntityNotFoundError("Original sale was not found.")
        if sale.sale_status == SaleStatus.CANCELLED.value:
            raise ReturnQuantityError("A cancelled sale cannot be returned.")

        sale_items = tuple(
            self.session.scalars(
                select(SaleItem)
                .where(
                    SaleItem.company_id == cmd.company_id,
                    SaleItem.sale_id == sale.id,
                    SaleItem.deleted_at.is_(None),
                )
                .order_by(SaleItem.id)
                .with_for_update()
            )
        )
        items_by_id = {item.id: item for item in sale_items}
        requested = self._aggregate_requested(cmd.lines, items_by_id)
        prior_quantities, prior_amounts = self._prior_returns(cmd.company_id, sale.id)
        for item_id, return_quantity in requested.items():
            already_returned = prior_quantities.get(item_id, Decimal("0.000"))
            if qty(already_returned + return_quantity) > items_by_id[item_id].quantity:
                raise ReturnQuantityError(
                    f"Return quantity exceeds the remaining quantity for sale item {item_id}."
                )

        item_amounts: dict[int, Decimal] = {}
        credit_total = ZERO
        for item_id, return_quantity in requested.items():
            item = items_by_id[item_id]
            remaining_quantity = qty(
                item.quantity - prior_quantities.get(item_id, Decimal("0.000"))
            )
            if return_quantity == remaining_quantity:
                amount = money(item.total_amount - prior_amounts.get(item_id, ZERO))
            else:
                ratio = return_quantity / item.quantity
                taxable = money(item.taxable_amount * ratio)
                cgst = money(item.cgst_amount * ratio)
                sgst = money(item.sgst_amount * ratio)
                igst = money(item.igst_amount * ratio)
                cess = money(item.cess_amount * ratio)
                amount = money(taxable + cgst + sgst + igst + cess)
            item_amounts[item_id] = amount
            credit_total = money(credit_total + amount)

        number, _ = InvoiceNumberService(self.session).allocate(
            cmd.company_id,
            sale.branch_id,
            sale.terminal_id,
            DocType.CREDIT_NOTE.value,
            cmd.on_date,
        )
        credit_note = CreditNote(
            company_id=cmd.company_id,
            branch_id=sale.branch_id,
            original_sale_id=sale.id,
            credit_note_number=number,
            reason=cmd.reason.strip().upper(),
            net_amount=credit_total,
            created_by=cmd.user_id,
        )
        self.session.add(credit_note)
        self.session.flush()

        product_ids = {items_by_id[item_id].product_id for item_id in requested}
        products = {
            product.id: product
            for product in self.session.scalars(
                select(Product)
                .where(
                    Product.company_id == cmd.company_id,
                    Product.id.in_(sorted(product_ids)),
                    Product.deleted_at.is_(None),
                )
                .order_by(Product.id)
                .with_for_update()
            )
        }
        if products.keys() != product_ids:
            raise EntityNotFoundError("A returned product was not found.")
        inventory = InventoryService(self.session, cmd.company_id)
        for item_id in sorted(requested):
            item = items_by_id[item_id]
            self.session.add(
                CreditNoteItem(
                    company_id=cmd.company_id,
                    credit_note_id=credit_note.id,
                    original_sale_item_id=item_id,
                    quantity=requested[item_id],
                    amount=item_amounts[item_id],
                    created_by=cmd.user_id,
                )
            )
            product = products[item.product_id]
            if product.is_inventory_tracked:
                inventory.record_movement(
                    product,
                    sale.branch_id,
                    requested[item_id],
                    "SALE_RETURN",
                    "credit_notes",
                    credit_note.id,
                    cmd.user_id,
                )

        fully_returned = all(
            qty(prior_quantities.get(item.id, Decimal("0.000")) + requested.get(item.id, ZERO))
            == item.quantity
            for item in sale_items
        )
        sale.sale_status = (
            SaleStatus.RETURNED.value if fully_returned else SaleStatus.PARTIALLY_RETURNED.value
        )
        if sale.customer_id is not None:
            customer = self.session.get(Customer, sale.customer_id, with_for_update=True)
            if customer is None or customer.company_id != cmd.company_id:
                raise EntityNotFoundError("Sale customer was not found.")
            reversed_points = qty(credit_total / self.loyalty_earn_divisor)
            customer.loyalty_points = max(
                Decimal("0.000"), customer.loyalty_points - reversed_points
            )
            customer.total_spent = max(ZERO, money(customer.total_spent - credit_total))
            if fully_returned and customer.total_orders > 0:
                customer.total_orders -= 1
            customer.row_version += 1
        self.session.flush()
        return credit_note

    @staticmethod
    def _aggregate_requested(
        lines: tuple[ReturnLineCommand, ...] | list[ReturnLineCommand],
        items_by_id: dict[int, SaleItem],
    ) -> dict[int, Decimal]:
        requested: dict[int, Decimal] = {}
        for index, line in enumerate(lines, start=1):
            if line.sale_item_id not in items_by_id:
                raise EntityNotFoundError(f"Sale item {line.sale_item_id} was not found.")
            try:
                amount = qty(to_decimal(line.quantity))
            except ValueError as exc:
                raise ValidationError(f"Return line {index} quantity must be numeric.") from exc
            if amount <= ZERO:
                raise ValidationError(f"Return line {index} quantity must be greater than zero.")
            requested[line.sale_item_id] = qty(
                requested.get(line.sale_item_id, Decimal("0.000")) + amount
            )
        return requested

    def _prior_returns(
        self, company_id: int, sale_id: int
    ) -> tuple[dict[int, Decimal], dict[int, Decimal]]:
        statement = (
            select(
                CreditNoteItem.original_sale_item_id,
                func.sum(CreditNoteItem.quantity),
                func.sum(CreditNoteItem.amount),
            )
            .join(CreditNote, CreditNote.id == CreditNoteItem.credit_note_id)
            .where(
                CreditNote.company_id == company_id,
                CreditNote.original_sale_id == sale_id,
                CreditNote.deleted_at.is_(None),
                CreditNoteItem.company_id == company_id,
                CreditNoteItem.deleted_at.is_(None),
            )
            .group_by(CreditNoteItem.original_sale_item_id)
        )
        rows = self.session.execute(statement)
        quantities: dict[int, Decimal] = {}
        amounts: dict[int, Decimal] = {}
        for item_id, returned_quantity, returned_amount in rows:
            quantities[item_id] = qty(returned_quantity)
            amounts[item_id] = money(returned_amount)
        return quantities, amounts
