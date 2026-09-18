"""Atomic inventory mutation and append-only ledger operations."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from vglpos.domain.models import Branch, Product, StockBatch, StockLedger
from vglpos.security.audit import record_audit_event
from vglpos.services.exceptions import (
    EntityNotFoundError,
    InsufficientStockError,
    ValidationError,
)
from vglpos.utils.money import money, qty, to_decimal

ZERO_QTY = Decimal("0.000")


class InventoryService:
    """Keep product balances and their audit ledger in the same transaction."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def record_movement(
        self,
        product: Product,
        branch_id: int,
        quantity_delta: object,
        txn_type: str,
        ref_table: str,
        ref_id: int | str,
        user_id: int,
        batch_id: int | None = None,
        unit_cost: object | None = None,
        *,
        notes: str | None = None,
    ) -> StockLedger:
        """Atomically update stock with SQL arithmetic and append its balance snapshot."""
        if product.company_id != self.company_id:
            raise ValidationError("Product does not belong to the active company.")
        try:
            delta = qty(to_decimal(quantity_delta))
        except ValueError as exc:
            raise ValidationError("Quantity delta must be numeric.") from exc
        if delta == ZERO_QTY:
            raise ValidationError("Quantity delta cannot be zero.")
        if not txn_type or not ref_table or not str(ref_id) or not user_id:
            raise ValidationError("Stock movement transaction, reference, and user are required.")
        branch_exists = self.session.scalar(
            select(Branch.id).where(
                Branch.id == branch_id,
                Branch.company_id == self.company_id,
                Branch.deleted_at.is_(None),
            )
        )
        if branch_exists is None:
            raise EntityNotFoundError("Inventory branch was not found.")
        if batch_id is not None:
            batch_exists = self.session.scalar(
                select(StockBatch.id).where(
                    StockBatch.id == batch_id,
                    StockBatch.company_id == self.company_id,
                    StockBatch.branch_id == branch_id,
                    StockBatch.product_id == product.id,
                    StockBatch.deleted_at.is_(None),
                )
            )
            if batch_exists is None:
                raise EntityNotFoundError("Inventory batch was not found.")

        statement = update(Product).where(
            Product.id == product.id,
            Product.company_id == self.company_id,
            Product.deleted_at.is_(None),
        )
        if product.is_inventory_tracked and delta < ZERO_QTY and not product.allow_negative_stock:
            statement = statement.where(Product.on_hand + delta >= Product.reserved_quantity)
        new_balance = self.session.scalar(
            statement.values(
                on_hand=Product.on_hand + delta,
                row_version=Product.row_version + 1,
            ).returning(Product.on_hand)
        )
        if new_balance is None:
            raise InsufficientStockError(
                f"Insufficient stock for product {product.id}; requested {-delta}."
            )

        try:
            movement_cost = money(product.cost_price if unit_cost is None else unit_cost)
        except ValueError as exc:
            raise ValidationError("Unit cost must be numeric.") from exc
        if movement_cost < 0:
            raise ValidationError("Unit cost cannot be negative.")
        ledger = StockLedger(
            company_id=self.company_id,
            branch_id=branch_id,
            product_id=product.id,
            batch_id=batch_id,
            txn_type=txn_type,
            reference_id=str(ref_id),
            reference_type=ref_table,
            quantity=delta,
            balance_after=qty(new_balance),
            unit_cost=movement_cost,
            notes=notes,
            created_by=user_id,
        )
        self.session.add(ledger)
        self.session.flush()
        return ledger

    def reserve_stock(self, product: Product, quantity: object) -> Decimal:
        """Increase reserved stock atomically without changing physical on-hand stock."""
        amount = self._positive_quantity(quantity)
        statement = update(Product).where(
            Product.id == product.id,
            Product.company_id == self.company_id,
            Product.deleted_at.is_(None),
        )
        if product.is_inventory_tracked and not product.allow_negative_stock:
            statement = statement.where(Product.on_hand - Product.reserved_quantity >= amount)
        reserved = self.session.scalar(
            statement.values(
                reserved_quantity=Product.reserved_quantity + amount,
                row_version=Product.row_version + 1,
            ).returning(Product.reserved_quantity)
        )
        if reserved is None:
            raise InsufficientStockError(f"Insufficient available stock for product {product.id}.")
        return qty(reserved)

    def release_reservation(self, product: Product, quantity: object) -> Decimal:
        """Release no more than the reserved balance in the caller's transaction."""
        amount = self._positive_quantity(quantity)
        reserved = self.session.scalar(
            update(Product)
            .where(
                Product.id == product.id,
                Product.company_id == self.company_id,
                Product.deleted_at.is_(None),
                Product.reserved_quantity >= amount,
            )
            .values(
                reserved_quantity=Product.reserved_quantity - amount,
                row_version=Product.row_version + 1,
            )
            .returning(Product.reserved_quantity)
        )
        if reserved is None:
            raise ValidationError("Cannot release more stock than is reserved.")
        return qty(reserved)

    def adjust_stock(
        self,
        product: Product,
        branch_id: int,
        quantity_delta: object,
        reason: str,
        user_id: int,
        *,
        ref_id: int | str = "MANUAL",
    ) -> StockLedger:
        """Record a reasoned manual adjustment atomically with its product balance."""
        if not reason.strip():
            raise ValidationError("A stock-adjustment reason is required.")
        ledger = self.record_movement(
            product,
            branch_id,
            quantity_delta,
            "ADJUSTMENT",
            "stock_adjustment",
            ref_id,
            user_id,
            notes=reason.strip(),
        )
        record_audit_event(
            self.session,
            company_id=self.company_id,
            user_id=user_id,
            action="STOCK_ADJUST",
            entity_type="StockLedger",
            entity_id=ledger.id,
            new_values={
                "product_id": product.id,
                "branch_id": branch_id,
                "quantity_delta": str(ledger.quantity),
                "balance_after": str(ledger.balance_after),
                "reason": reason.strip(),
            },
        )
        return ledger

    def weighted_average_cost_update(
        self,
        product: Product,
        received_quantity: object,
        received_unit_cost: object,
    ) -> Decimal:
        """Update weighted cost under a row lock without committing the caller's work."""
        received = self._positive_quantity(received_quantity)
        try:
            incoming_cost = money(received_unit_cost)
        except ValueError as exc:
            raise ValidationError("Received unit cost must be numeric.") from exc
        if incoming_cost < 0:
            raise ValidationError("Received unit cost cannot be negative.")
        current = self.session.get(Product, product.id, with_for_update=True)
        if (
            current is None
            or current.company_id != self.company_id
            or current.deleted_at is not None
        ):
            raise ValidationError("Product was not found for weighted-average update.")
        total_quantity = qty(current.on_hand + received)
        if total_quantity <= ZERO_QTY:
            raise ValidationError("Weighted-average quantity must remain positive.")
        weighted_cost = money(
            (current.on_hand * current.cost_price + received * incoming_cost) / total_quantity
        )
        self.session.execute(
            update(Product)
            .where(Product.id == current.id, Product.company_id == self.company_id)
            .values(cost_price=weighted_cost, row_version=Product.row_version + 1)
        )
        self.session.flush()
        return weighted_cost

    @staticmethod
    def _positive_quantity(value: object) -> Decimal:
        try:
            amount = qty(to_decimal(value))
        except ValueError as exc:
            raise ValidationError("Quantity must be numeric.") from exc
        if amount <= ZERO_QTY:
            raise ValidationError("Quantity must be greater than zero.")
        return amount
