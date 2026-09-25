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
    CreditNoteItemBatch,
    Customer,
    LoyaltyLedger,
    Product,
    Sale,
    SaleItem,
    SaleItemBatch,
    SalePayment,
    StockBatch,
)
from vglpos.services.exceptions import (
    CheckoutError,
    ConflictError,
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

    def __init__(self, session: Session) -> None:
        self.session = session

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
            note_date=cmd.on_date,
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
            credit_item = CreditNoteItem(
                company_id=cmd.company_id,
                credit_note_id=credit_note.id,
                original_sale_item_id=item_id,
                quantity=requested[item_id],
                amount=item_amounts[item_id],
                created_by=cmd.user_id,
            )
            self.session.add(credit_item)
            self.session.flush()
            product = products[item.product_id]
            restored_batches = False
            if product.is_inventory_tracked:
                restored_batches = self._restore_original_batches(
                    cmd=cmd,
                    sale=sale,
                    sale_item=item,
                    credit_note=credit_note,
                    credit_item=credit_item,
                    product=product,
                    return_quantity=requested[item_id],
                    inventory=inventory,
                )
            if product.is_inventory_tracked and not restored_batches:
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
            self._reverse_loyalty(
                cmd=cmd,
                sale=sale,
                credit_note=credit_note,
                customer=customer,
                credit_total=credit_total,
                fully_returned=fully_returned,
            )
            self._reverse_credit_outstanding(
                sale=sale,
                customer=customer,
                credit_total=credit_total,
                prior_return_total=money(sum(prior_amounts.values(), ZERO)),
                fully_returned=fully_returned,
            )
            customer.total_spent = max(ZERO, money(customer.total_spent - credit_total))
            if fully_returned and customer.total_orders > 0:
                customer.total_orders -= 1
            customer.row_version += 1
        self.session.flush()
        return credit_note

    def _restore_original_batches(
        self,
        *,
        cmd: CreateCreditNoteCommand,
        sale: Sale,
        sale_item: SaleItem,
        credit_note: CreditNote,
        credit_item: CreditNoteItem,
        product: Product,
        return_quantity: Decimal,
        inventory: InventoryService,
    ) -> bool:
        """Restore a return across the immutable lots consumed by the original line."""
        allocations = tuple(
            self.session.scalars(
                select(SaleItemBatch)
                .where(
                    SaleItemBatch.company_id == cmd.company_id,
                    SaleItemBatch.sale_item_id == sale_item.id,
                    SaleItemBatch.deleted_at.is_(None),
                )
                .order_by(SaleItemBatch.id)
            )
        )
        if not allocations:
            return False
        prior = {
            allocation_id: qty(restored)
            for allocation_id, restored in self.session.execute(
                select(
                    CreditNoteItemBatch.sale_item_batch_id,
                    func.sum(CreditNoteItemBatch.quantity),
                )
                .join(
                    CreditNoteItem,
                    CreditNoteItem.id == CreditNoteItemBatch.credit_note_item_id,
                )
                .where(
                    CreditNoteItemBatch.company_id == cmd.company_id,
                    CreditNoteItemBatch.deleted_at.is_(None),
                    CreditNoteItem.company_id == cmd.company_id,
                    CreditNoteItem.original_sale_item_id == sale_item.id,
                    CreditNoteItem.deleted_at.is_(None),
                )
                .group_by(CreditNoteItemBatch.sale_item_batch_id)
            )
        }
        remaining = qty(return_quantity)
        for allocation in allocations:
            restorable = qty(allocation.quantity - prior.get(allocation.id, Decimal("0.000")))
            restored = min(remaining, restorable)
            if restored <= ZERO:
                continue
            batch = self.session.scalar(
                select(StockBatch)
                .where(
                    StockBatch.id == allocation.batch_id,
                    StockBatch.company_id == cmd.company_id,
                    StockBatch.branch_id == sale.branch_id,
                    StockBatch.product_id == sale_item.product_id,
                    StockBatch.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if batch is None:
                raise EntityNotFoundError("The original sale batch was not found.")
            batch.quantity_available = qty(batch.quantity_available + restored)
            batch.row_version += 1
            self.session.add(
                CreditNoteItemBatch(
                    company_id=cmd.company_id,
                    credit_note_item_id=credit_item.id,
                    sale_item_batch_id=allocation.id,
                    batch_id=batch.id,
                    quantity=restored,
                    unit_cost=allocation.unit_cost,
                    created_by=cmd.user_id,
                )
            )
            inventory.record_movement(
                product,
                sale.branch_id,
                restored,
                "SALE_RETURN",
                "credit_notes",
                credit_note.id,
                cmd.user_id,
                batch_id=batch.id,
                unit_cost=allocation.unit_cost,
                notes=f"Original sale item {sale_item.id}",
            )
            remaining = qty(remaining - restored)
            if remaining <= ZERO:
                break
        if remaining > ZERO:
            raise ConflictError("Original sale batch allocations cannot satisfy the return.")
        return True

    def _reverse_loyalty(
        self,
        *,
        cmd: CreateCreditNoteCommand,
        sale: Sale,
        credit_note: CreditNote,
        customer: Customer,
        credit_total: Decimal,
        fully_returned: bool,
    ) -> None:
        """Reverse earned and redeemed points proportionally with an immutable ledger."""
        original_rows = self.session.execute(
            select(LoyaltyLedger.movement_type, func.sum(LoyaltyLedger.points))
            .where(
                LoyaltyLedger.company_id == cmd.company_id,
                LoyaltyLedger.sale_id == sale.id,
                LoyaltyLedger.credit_note_id.is_(None),
                LoyaltyLedger.deleted_at.is_(None),
            )
            .group_by(LoyaltyLedger.movement_type)
        ).all()
        originals = {movement_type: qty(points) for movement_type, points in original_rows}
        prior_rows = self.session.execute(
            select(LoyaltyLedger.movement_type, func.sum(LoyaltyLedger.points))
            .where(
                LoyaltyLedger.company_id == cmd.company_id,
                LoyaltyLedger.sale_id == sale.id,
                LoyaltyLedger.credit_note_id.is_not(None),
                LoyaltyLedger.deleted_at.is_(None),
            )
            .group_by(LoyaltyLedger.movement_type)
        ).all()
        prior = {movement_type: qty(points) for movement_type, points in prior_rows}
        ratio = credit_total / sale.net_amount if sale.net_amount > ZERO else ZERO
        original_earned = max(Decimal("0.000"), originals.get("EARN", Decimal("0.000")))
        original_redeemed = abs(min(Decimal("0.000"), originals.get("REDEEM", Decimal("0.000"))))
        earned_already_reversed = abs(
            min(Decimal("0.000"), prior.get("EARN_REVERSAL", Decimal("0.000")))
        )
        redeemed_already_restored = max(
            Decimal("0.000"), prior.get("REDEEM_REVERSAL", Decimal("0.000"))
        )
        earned_reversal = (
            qty(original_earned - earned_already_reversed)
            if fully_returned
            else qty(original_earned * ratio)
        )
        redeemed_restoration = (
            qty(original_redeemed - redeemed_already_restored)
            if fully_returned
            else qty(original_redeemed * ratio)
        )
        balance = qty(customer.loyalty_points)
        if earned_reversal > ZERO:
            balance = qty(balance - earned_reversal)
            self.session.add(
                LoyaltyLedger(
                    company_id=cmd.company_id,
                    customer_id=customer.id,
                    sale_id=sale.id,
                    credit_note_id=credit_note.id,
                    movement_type="EARN_REVERSAL",
                    points=-earned_reversal,
                    balance_after=balance,
                    description=f"Earn reversal on {credit_note.credit_note_number}",
                    created_by=cmd.user_id,
                )
            )
        if redeemed_restoration > ZERO:
            balance = qty(balance + redeemed_restoration)
            self.session.add(
                LoyaltyLedger(
                    company_id=cmd.company_id,
                    customer_id=customer.id,
                    sale_id=sale.id,
                    credit_note_id=credit_note.id,
                    movement_type="REDEEM_REVERSAL",
                    points=redeemed_restoration,
                    balance_after=balance,
                    description=f"Redemption reversal on {credit_note.credit_note_number}",
                    created_by=cmd.user_id,
                )
            )
        customer.loyalty_points = balance

    def _reverse_credit_outstanding(
        self,
        *,
        sale: Sale,
        customer: Customer,
        credit_total: Decimal,
        prior_return_total: Decimal,
        fully_returned: bool,
    ) -> None:
        """Reduce khata outstanding by the returned share of the original credit tender."""
        original_credit = money(
            self.session.scalar(
                select(func.coalesce(func.sum(SalePayment.amount), ZERO)).where(
                    SalePayment.company_id == sale.company_id,
                    SalePayment.sale_id == sale.id,
                    SalePayment.payment_method == "CREDIT",
                    SalePayment.deleted_at.is_(None),
                )
            )
            or ZERO
        )
        if original_credit <= ZERO or sale.net_amount <= ZERO:
            return
        previously_reversed = money(original_credit * prior_return_total / sale.net_amount)
        if fully_returned:
            reversal = money(original_credit - previously_reversed)
        else:
            cumulative_return = money(prior_return_total + credit_total)
            cumulative_reversal = money(original_credit * cumulative_return / sale.net_amount)
            reversal = money(cumulative_reversal - previously_reversed)
        customer.outstanding_balance = max(
            ZERO, money(customer.outstanding_balance - max(ZERO, reversal))
        )

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
