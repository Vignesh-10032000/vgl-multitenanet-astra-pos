"""Supplier purchasing, three-way matching, landed cost, and payable ledgers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.enums import DocType, LedgerTxnType
from vglpos.domain.models import (
    Branch,
    Company,
    GoodsReceipt,
    GoodsReceiptItem,
    Product,
    Purchase,
    PurchaseItem,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReturn,
    PurchaseReturnItem,
    StockBatch,
    Supplier,
    SupplierLedger,
)
from vglpos.security.audit import record_audit_event
from vglpos.services.exceptions import (
    ConflictError,
    EntityNotFoundError,
    ValidationError,
)
from vglpos.services.inventory_service import InventoryService
from vglpos.services.invoice_number_service import InvoiceNumberService
from vglpos.utils.money import ZERO, apportion, money, qty, to_decimal

logger = logging.getLogger(__name__)
ZERO_QTY = Decimal("0.000")


@dataclass(frozen=True, slots=True)
class SupplierCommand:
    """Carry a tenant-scoped supplier master into the service layer."""

    company_id: int
    code: str
    name: str
    phone: str
    state_code: str
    payment_terms_days: int = 30
    gstin: str | None = None
    pan: str | None = None
    email: str | None = None
    contact_person: str | None = None
    address: str | None = None
    user_id: int = 0


@dataclass(frozen=True, slots=True)
class PurchaseOrderLineCommand:
    product_id: int
    quantity: object
    unit_cost: object
    tax_rate: object


@dataclass(frozen=True, slots=True)
class CreatePurchaseOrderCommand:
    company_id: int
    branch_id: int
    terminal_id: int
    supplier_id: int
    user_id: int
    order_date: date
    lines: tuple[PurchaseOrderLineCommand, ...] | list[PurchaseOrderLineCommand]
    expected_date: date | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class GoodsReceiptLineCommand:
    purchase_order_item_id: int
    quantity: object
    unit_cost: object
    batch_number: str | None = None
    mfg_date: date | None = None
    expiry_date: date | None = None


@dataclass(frozen=True, slots=True)
class CreateGoodsReceiptCommand:
    company_id: int
    branch_id: int
    terminal_id: int
    purchase_order_id: int
    user_id: int
    received_at: datetime
    lines: tuple[GoodsReceiptLineCommand, ...] | list[GoodsReceiptLineCommand]
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class PurchaseInvoiceLineCommand:
    goods_receipt_item_id: int
    billed_quantity: object
    unit_cost: object


@dataclass(frozen=True, slots=True)
class PostPurchaseInvoiceCommand:
    company_id: int
    branch_id: int
    goods_receipt_id: int
    supplier_invoice_number: str
    invoice_date: date
    user_id: int
    lines: tuple[PurchaseInvoiceLineCommand, ...] | list[PurchaseInvoiceLineCommand]
    landed_cost: object = ZERO
    landed_cost_method: str = "VALUE"


@dataclass(frozen=True, slots=True)
class PurchaseCostPreviewLine:
    goods_receipt_item_id: int
    purchase_order_item_id: int
    product_id: int
    received_quantity: Decimal
    billed_quantity: Decimal
    expected_unit_cost: Decimal
    invoice_unit_cost: Decimal
    quantity_variance_percent: Decimal
    price_variance_percent: Decimal
    landed_cost_amount: Decimal
    unit_landed_cost: Decimal
    old_average_cost: Decimal
    new_average_cost: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal


@dataclass(frozen=True, slots=True)
class PurchaseInvoicePreview:
    supplier_id: int
    purchase_order_id: int
    goods_receipt_id: int
    lines: tuple[PurchaseCostPreviewLine, ...]
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    landed_cost_amount: Decimal
    total_amount: Decimal


@dataclass(frozen=True, slots=True)
class PurchaseReturnLineCommand:
    purchase_item_id: int
    quantity: object


@dataclass(frozen=True, slots=True)
class PurchaseReturnCommand:
    company_id: int
    branch_id: int
    terminal_id: int
    purchase_id: int
    user_id: int
    return_date: date
    reason: str
    lines: tuple[PurchaseReturnLineCommand, ...] | list[PurchaseReturnLineCommand]


@dataclass(frozen=True, slots=True)
class SupplierPaymentCommand:
    company_id: int
    supplier_id: int
    user_id: int
    payment_date: date
    amount: object
    reference: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class _InvoiceContext:
    company: Company
    branch: Branch
    supplier: Supplier
    order: PurchaseOrder
    receipt: GoodsReceipt
    receipt_items: dict[int, GoodsReceiptItem]
    order_items: dict[int, PurchaseOrderItem]
    products: dict[int, Product]


class PurchaseService:
    """Own every stock and payable mutation arising from supplier documents."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def create_supplier(self, command: SupplierCommand) -> Supplier:
        """Create a GST-aware supplier without allowing caller-controlled tenancy."""
        self._require_company(command.company_id)
        code = command.code.strip().upper()
        name = command.name.strip()
        phone = command.phone.strip()
        if not code or not name or not phone:
            raise ValidationError("Supplier code, name, and phone are required.")
        if len(command.state_code) != 2 or not command.state_code.isdigit():
            raise ValidationError("Supplier state code must contain two digits.")
        if command.payment_terms_days < 0 or command.payment_terms_days > 3650:
            raise ValidationError("Supplier payment terms must be between 0 and 3650 days.")
        supplier = Supplier(
            company_id=self.company_id,
            code=code,
            name=name,
            phone=phone,
            state_code=command.state_code,
            payment_terms_days=command.payment_terms_days,
            gstin=command.gstin,
            pan=command.pan,
            email=command.email,
            contact_person=command.contact_person,
            address=command.address,
            created_by=command.user_id or None,
        )
        self.session.add(supplier)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Supplier code already exists.") from exc
        self.session.refresh(supplier)
        return supplier

    def create_purchase_order(self, command: CreatePurchaseOrderCommand) -> PurchaseOrder:
        """Persist an expected quantity and cost baseline for later three-way matching."""
        self._require_command_company(command.company_id)
        if not 1 <= len(command.lines) <= 500:
            raise ValidationError("Purchase order must contain between 1 and 500 lines.")
        branch = self._require_branch(command.branch_id)
        supplier = self._require_supplier(command.supplier_id)
        if command.expected_date is not None and command.expected_date < command.order_date:
            raise ValidationError("Expected date cannot be before the order date.")
        products = self._load_products({line.product_id for line in command.lines})
        normalized: list[tuple[Product, Decimal, Decimal, Decimal, Decimal, Decimal]] = []
        for index, line in enumerate(command.lines, start=1):
            quantity = self._positive_qty(line.quantity, f"Line {index} quantity")
            unit_cost = self._nonnegative_money(line.unit_cost, f"Line {index} unit cost")
            tax_rate = self._rate(line.tax_rate, f"Line {index} tax rate")
            taxable = money(quantity * unit_cost)
            tax_amount = money(taxable * tax_rate / Decimal("100"))
            normalized.append(
                (products[line.product_id], quantity, unit_cost, tax_rate, taxable, tax_amount)
            )
        taxable_total = money(sum((line[4] for line in normalized), ZERO))
        tax_total = money(sum((line[5] for line in normalized), ZERO))
        order_number, _ = InvoiceNumberService(self.session).allocate(
            self.company_id,
            branch.id,
            command.terminal_id,
            DocType.PURCHASE_ORDER.value,
            command.order_date,
        )
        order = PurchaseOrder(
            company_id=self.company_id,
            branch_id=branch.id,
            supplier_id=supplier.id,
            order_number=order_number,
            order_date=command.order_date,
            expected_date=command.expected_date,
            status="OPEN",
            taxable_amount=taxable_total,
            tax_amount=tax_total,
            total_amount=money(taxable_total + tax_total),
            notes=command.notes,
            created_by=command.user_id,
        )
        self.session.add(order)
        self.session.flush()
        for line_number, (product, quantity, unit_cost, tax_rate, taxable, tax_amount) in enumerate(
            normalized, start=1
        ):
            self.session.add(
                PurchaseOrderItem(
                    company_id=self.company_id,
                    purchase_order_id=order.id,
                    product_id=product.id,
                    line_number=line_number,
                    ordered_quantity=quantity,
                    unit_cost=unit_cost,
                    tax_rate=tax_rate,
                    total_amount=money(taxable + tax_amount),
                    created_by=command.user_id,
                )
            )
        self._audit(command.user_id, "PURCHASE_ORDER_CREATE", "PurchaseOrder", order.id)
        self.session.commit()
        self.session.refresh(order)
        return order

    def receive_goods(self, command: CreateGoodsReceiptCommand) -> GoodsReceipt:
        """Record physical lots only after quantity and price tolerances are satisfied."""
        self._require_command_company(command.company_id)
        if not 1 <= len(command.lines) <= 500:
            raise ValidationError("Goods receipt must contain between 1 and 500 lines.")
        company = self._require_company(self.company_id)
        order = self.session.scalar(
            select(PurchaseOrder)
            .where(
                PurchaseOrder.id == command.purchase_order_id,
                PurchaseOrder.company_id == self.company_id,
                PurchaseOrder.branch_id == command.branch_id,
                PurchaseOrder.deleted_at.is_(None),
                PurchaseOrder.status.in_(("OPEN", "PART_RECEIVED")),
            )
            .with_for_update()
        )
        if order is None:
            raise EntityNotFoundError("Open purchase order was not found.")
        order_items = {
            item.id: item
            for item in self.session.scalars(
                select(PurchaseOrderItem).where(
                    PurchaseOrderItem.company_id == self.company_id,
                    PurchaseOrderItem.purchase_order_id == order.id,
                    PurchaseOrderItem.deleted_at.is_(None),
                )
            )
        }
        if len({line.purchase_order_item_id for line in command.lines}) != len(command.lines):
            raise ValidationError("A purchase-order line can appear only once per receipt.")
        for index, line in enumerate(command.lines, start=1):
            item = order_items.get(line.purchase_order_item_id)
            if item is None:
                raise EntityNotFoundError(f"Purchase-order line {index} was not found.")
            received = self._positive_qty(line.quantity, f"Line {index} quantity")
            unit_cost = self._nonnegative_money(line.unit_cost, f"Line {index} unit cost")
            prior = qty(
                self.session.scalar(
                    select(func.coalesce(func.sum(GoodsReceiptItem.received_quantity), 0))
                    .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptItem.goods_receipt_id)
                    .where(
                        GoodsReceiptItem.company_id == self.company_id,
                        GoodsReceiptItem.purchase_order_item_id == item.id,
                        GoodsReceiptItem.deleted_at.is_(None),
                        GoodsReceipt.deleted_at.is_(None),
                    )
                )
            )
            maximum = qty(
                item.ordered_quantity
                * (Decimal("1") + company.purchase_quantity_tolerance_percent / Decimal("100"))
            )
            if qty(prior + received) > maximum:
                raise ConflictError("Received quantity exceeds the configured purchase tolerance.")
            self._enforce_price_tolerance(
                expected=item.unit_cost,
                actual=unit_cost,
                tolerance=company.purchase_price_tolerance_percent,
            )
            if (
                line.expiry_date is not None
                and line.mfg_date is not None
                and line.expiry_date <= line.mfg_date
            ):
                raise ValidationError("Batch expiry date must be after manufacture date.")
        grn_number, _ = InvoiceNumberService(self.session).allocate(
            self.company_id,
            command.branch_id,
            command.terminal_id,
            DocType.GOODS_RECEIPT.value,
            command.received_at.date(),
        )
        receipt = GoodsReceipt(
            company_id=self.company_id,
            branch_id=command.branch_id,
            supplier_id=order.supplier_id,
            purchase_order_id=order.id,
            grn_number=grn_number,
            received_at=command.received_at,
            status="RECEIVED",
            notes=command.notes,
            created_by=command.user_id,
        )
        self.session.add(receipt)
        self.session.flush()
        for line in command.lines:
            item = order_items[line.purchase_order_item_id]
            self.session.add(
                GoodsReceiptItem(
                    company_id=self.company_id,
                    goods_receipt_id=receipt.id,
                    purchase_order_item_id=item.id,
                    product_id=item.product_id,
                    batch_number=line.batch_number.strip() if line.batch_number else None,
                    mfg_date=line.mfg_date,
                    expiry_date=line.expiry_date,
                    received_quantity=self._positive_qty(line.quantity, "Received quantity"),
                    unit_cost=self._nonnegative_money(line.unit_cost, "Received unit cost"),
                    created_by=command.user_id,
                )
            )
        order.status = "PART_RECEIVED"
        self._audit(command.user_id, "GOODS_RECEIPT_CREATE", "GoodsReceipt", receipt.id)
        self.session.commit()
        self.session.refresh(receipt)
        return receipt

    def preview_invoice(self, command: PostPurchaseInvoiceCommand) -> PurchaseInvoicePreview:
        """Expose matching variances and weighted-cost changes without mutating stock."""
        context = self._invoice_context(command)
        return self._build_invoice_preview(command, context)

    def post_invoice(self, command: PostPurchaseInvoiceCommand) -> Purchase:
        """Post one matched supplier invoice atomically with batches, stock, and payables."""
        context = self._invoice_context(command, for_update=True)
        preview = self._build_invoice_preview(command, context)
        invoice_number = command.supplier_invoice_number.strip()
        if not invoice_number:
            raise ValidationError("Supplier invoice number is required.")
        due_date = command.invoice_date + timedelta(days=context.supplier.payment_terms_days)
        purchase = Purchase(
            company_id=self.company_id,
            branch_id=context.branch.id,
            supplier_id=context.supplier.id,
            purchase_order_id=context.order.id,
            goods_receipt_id=context.receipt.id,
            invoice_number=invoice_number,
            invoice_date=command.invoice_date,
            due_date=due_date,
            status="POSTED",
            taxable_amount=preview.taxable_amount,
            cgst_amount=preview.cgst_amount,
            sgst_amount=preview.sgst_amount,
            igst_amount=preview.igst_amount,
            cess_amount=ZERO,
            landed_cost_amount=preview.landed_cost_amount,
            total_amount=preview.total_amount,
            amount_paid=ZERO,
            outstanding_amount=preview.total_amount,
            created_by=command.user_id,
        )
        self.session.add(purchase)
        self.session.flush()
        inventory = InventoryService(self.session, self.company_id)
        for row in preview.lines:
            receipt_item = context.receipt_items[row.goods_receipt_item_id]
            order_item = context.order_items[row.purchase_order_item_id]
            product = context.products[row.product_id]
            batch = self._receive_batch(
                product=product,
                branch_id=context.branch.id,
                receipt_item=receipt_item,
                unit_landed_cost=row.unit_landed_cost,
                user_id=command.user_id,
            )
            inventory.weighted_average_cost_update(
                product, row.received_quantity, row.unit_landed_cost
            )
            inventory.record_movement(
                product,
                context.branch.id,
                row.received_quantity,
                LedgerTxnType.PURCHASE.value,
                "purchases",
                purchase.id,
                command.user_id,
                batch_id=batch.id if batch is not None else None,
                unit_cost=row.unit_landed_cost,
            )
            tax_amount = row.tax_amount
            interstate = context.supplier.state_code != context.branch.state_code
            cgst = ZERO if interstate else money(tax_amount / 2)
            sgst = ZERO if interstate else money(tax_amount - cgst)
            igst = tax_amount if interstate else ZERO
            self.session.add(
                PurchaseItem(
                    company_id=self.company_id,
                    purchase_id=purchase.id,
                    product_id=product.id,
                    batch_number=receipt_item.batch_number,
                    batch_id=batch.id if batch is not None else None,
                    quantity=row.billed_quantity,
                    unit_cost=row.invoice_unit_cost,
                    tax_rate=order_item.tax_rate,
                    taxable_amount=row.taxable_amount,
                    cgst_amount=cgst,
                    sgst_amount=sgst,
                    igst_amount=igst,
                    cess_amount=ZERO,
                    landed_cost_amount=row.landed_cost_amount,
                    unit_landed_cost=row.unit_landed_cost,
                    total_amount=money(row.taxable_amount + tax_amount + row.landed_cost_amount),
                    created_by=command.user_id,
                )
            )
        context.order.status = "INVOICED"
        context.receipt.status = "MATCHED"
        self._post_supplier_movement(
            supplier=context.supplier,
            txn_date=command.invoice_date,
            txn_type="INVOICE",
            reference_type="purchases",
            reference_id=purchase.id,
            debit=ZERO,
            credit=preview.total_amount,
            due_date=due_date,
            user_id=command.user_id,
        )
        self._audit(command.user_id, "PURCHASE_POST", "Purchase", purchase.id)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            logger.exception(
                "Purchase invoice persistence conflict",
                extra={"company_id": self.company_id, "goods_receipt_id": command.goods_receipt_id},
            )
            raise ConflictError(
                "Supplier invoice already exists or was concurrently posted."
            ) from exc
        self.session.refresh(purchase)
        return purchase

    def create_purchase_return(self, command: PurchaseReturnCommand) -> PurchaseReturn:
        """Issue a debit note while reversing stock and supplier liability in one transaction."""
        self._require_command_company(command.company_id)
        reason = command.reason.strip()
        if not reason or not command.lines:
            raise ValidationError("Purchase return requires a reason and at least one line.")
        purchase = self.session.scalar(
            select(Purchase)
            .where(
                Purchase.id == command.purchase_id,
                Purchase.company_id == self.company_id,
                Purchase.branch_id == command.branch_id,
                Purchase.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if purchase is None:
            raise EntityNotFoundError("Purchase was not found.")
        supplier = self._require_supplier(purchase.supplier_id, for_update=True)
        items = {
            item.id: item
            for item in self.session.scalars(
                select(PurchaseItem).where(
                    PurchaseItem.company_id == self.company_id,
                    PurchaseItem.purchase_id == purchase.id,
                    PurchaseItem.deleted_at.is_(None),
                )
            )
        }
        products = self._load_products(
            {item.product_id for item in items.values()}, for_update=True
        )
        normalized: list[tuple[PurchaseItem, Decimal, Decimal, Decimal]] = []
        for line in command.lines:
            item = items.get(line.purchase_item_id)
            if item is None:
                raise EntityNotFoundError("Purchase return line was not found.")
            amount = self._positive_qty(line.quantity, "Return quantity")
            already_returned = qty(
                self.session.scalar(
                    select(func.coalesce(func.sum(PurchaseReturnItem.quantity), 0)).where(
                        PurchaseReturnItem.company_id == self.company_id,
                        PurchaseReturnItem.purchase_item_id == item.id,
                        PurchaseReturnItem.deleted_at.is_(None),
                    )
                )
            )
            if qty(already_returned + amount) > item.quantity:
                raise ConflictError("Purchase return quantity exceeds the original line.")
            taxable = money(amount * item.unit_cost)
            tax_amount = money(taxable * item.tax_rate / Decimal("100"))
            normalized.append((item, amount, taxable, tax_amount))
        taxable_total = money(sum((row[2] for row in normalized), ZERO))
        tax_total = money(sum((row[3] for row in normalized), ZERO))
        total = money(taxable_total + tax_total)
        debit_number, _ = InvoiceNumberService(self.session).allocate(
            self.company_id,
            command.branch_id,
            command.terminal_id,
            DocType.DEBIT_NOTE.value,
            command.return_date,
        )
        interstate = supplier.state_code != self._require_branch(command.branch_id).state_code
        cgst = ZERO if interstate else money(tax_total / 2)
        sgst = ZERO if interstate else money(tax_total - cgst)
        debit_note = PurchaseReturn(
            company_id=self.company_id,
            branch_id=command.branch_id,
            supplier_id=supplier.id,
            purchase_id=purchase.id,
            debit_note_number=debit_number,
            return_date=command.return_date,
            reason=reason,
            taxable_amount=taxable_total,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=tax_total if interstate else ZERO,
            cess_amount=ZERO,
            total_amount=total,
            created_by=command.user_id,
        )
        self.session.add(debit_note)
        self.session.flush()
        inventory = InventoryService(self.session, self.company_id)
        for item, amount, taxable, tax_amount in normalized:
            product = products[item.product_id]
            if item.batch_id is not None:
                available = self.session.scalar(
                    select(StockBatch)
                    .where(
                        StockBatch.id == item.batch_id,
                        StockBatch.company_id == self.company_id,
                        StockBatch.branch_id == command.branch_id,
                        StockBatch.deleted_at.is_(None),
                    )
                    .with_for_update()
                )
                if available is None or available.quantity_available < amount:
                    raise ConflictError("Purchase-return batch does not have enough stock.")
                available.quantity_available = qty(available.quantity_available - amount)
            inventory.record_movement(
                product,
                command.branch_id,
                -amount,
                LedgerTxnType.PURCHASE_RETURN.value,
                "purchase_returns",
                debit_note.id,
                command.user_id,
                batch_id=item.batch_id,
                unit_cost=item.unit_landed_cost,
            )
            self.session.add(
                PurchaseReturnItem(
                    company_id=self.company_id,
                    purchase_return_id=debit_note.id,
                    purchase_item_id=item.id,
                    product_id=item.product_id,
                    batch_id=item.batch_id,
                    quantity=amount,
                    unit_cost=item.unit_cost,
                    taxable_amount=taxable,
                    tax_amount=tax_amount,
                    total_amount=money(taxable + tax_amount),
                    created_by=command.user_id,
                )
            )
        purchase.outstanding_amount = money(max(ZERO, purchase.outstanding_amount - total))
        self._post_supplier_movement(
            supplier=supplier,
            txn_date=command.return_date,
            txn_type="DEBIT_NOTE",
            reference_type="purchase_returns",
            reference_id=debit_note.id,
            debit=total,
            credit=ZERO,
            due_date=None,
            user_id=command.user_id,
        )
        self._audit(command.user_id, "PURCHASE_RETURN", "PurchaseReturn", debit_note.id)
        self.session.commit()
        self.session.refresh(debit_note)
        return debit_note

    def record_supplier_payment(self, command: SupplierPaymentCommand) -> SupplierLedger:
        """Reduce a supplier payable through an attributable ledger movement."""
        self._require_command_company(command.company_id)
        amount = self._positive_money(command.amount, "Supplier payment")
        supplier = self._require_supplier(command.supplier_id, for_update=True)
        if amount > supplier.outstanding_balance:
            raise ConflictError("Supplier payment exceeds the outstanding balance.")
        movement = self._post_supplier_movement(
            supplier=supplier,
            txn_date=command.payment_date,
            txn_type="PAYMENT",
            reference_type="supplier_payment",
            reference_id=command.reference.strip(),
            debit=amount,
            credit=ZERO,
            due_date=None,
            user_id=command.user_id,
            notes=command.notes,
        )
        self.session.commit()
        self.session.refresh(movement)
        return movement

    def _invoice_context(
        self, command: PostPurchaseInvoiceCommand, *, for_update: bool = False
    ) -> _InvoiceContext:
        self._require_command_company(command.company_id)
        if not 1 <= len(command.lines) <= 500:
            raise ValidationError("Supplier invoice must contain between 1 and 500 lines.")
        if len({line.goods_receipt_item_id for line in command.lines}) != len(command.lines):
            raise ValidationError("A goods-receipt line can appear only once per invoice.")
        company = self._require_company(self.company_id)
        branch = self._require_branch(command.branch_id)
        receipt_query = select(GoodsReceipt).where(
            GoodsReceipt.id == command.goods_receipt_id,
            GoodsReceipt.company_id == self.company_id,
            GoodsReceipt.branch_id == branch.id,
            GoodsReceipt.deleted_at.is_(None),
            GoodsReceipt.status == "RECEIVED",
        )
        if for_update:
            receipt_query = receipt_query.with_for_update()
        receipt = self.session.scalar(receipt_query)
        if receipt is None:
            raise EntityNotFoundError("Unmatched goods receipt was not found.")
        supplier = self._require_supplier(receipt.supplier_id, for_update=for_update)
        order = self.session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == receipt.purchase_order_id,
                PurchaseOrder.company_id == self.company_id,
                PurchaseOrder.deleted_at.is_(None),
            )
        )
        if order is None:
            raise EntityNotFoundError("Purchase order was not found.")
        receipt_items = {
            item.id: item
            for item in self.session.scalars(
                select(GoodsReceiptItem).where(
                    GoodsReceiptItem.company_id == self.company_id,
                    GoodsReceiptItem.goods_receipt_id == receipt.id,
                    GoodsReceiptItem.deleted_at.is_(None),
                )
            )
        }
        requested_ids = {line.goods_receipt_item_id for line in command.lines}
        if requested_ids != receipt_items.keys():
            raise ValidationError(
                "Supplier invoice must match every goods-receipt line exactly once."
            )
        order_items = {
            item.id: item
            for item in self.session.scalars(
                select(PurchaseOrderItem).where(
                    PurchaseOrderItem.company_id == self.company_id,
                    PurchaseOrderItem.purchase_order_id == order.id,
                    PurchaseOrderItem.deleted_at.is_(None),
                )
            )
        }
        products = self._load_products(
            {item.product_id for item in receipt_items.values()}, for_update=for_update
        )
        return _InvoiceContext(
            company, branch, supplier, order, receipt, receipt_items, order_items, products
        )

    def _build_invoice_preview(
        self, command: PostPurchaseInvoiceCommand, context: _InvoiceContext
    ) -> PurchaseInvoicePreview:
        landed_total = self._nonnegative_money(command.landed_cost, "Landed cost")
        method = command.landed_cost_method.strip().upper()
        if method not in {"VALUE", "WEIGHT"}:
            raise ValidationError("Landed-cost method must be VALUE or WEIGHT.")
        prepared: list[
            tuple[
                PurchaseInvoiceLineCommand,
                GoodsReceiptItem,
                PurchaseOrderItem,
                Product,
                Decimal,
                Decimal,
                Decimal,
            ]
        ] = []
        weights: list[Decimal] = []
        for index, line in enumerate(command.lines, start=1):
            receipt_item = context.receipt_items[line.goods_receipt_item_id]
            order_item = context.order_items[receipt_item.purchase_order_item_id]
            product = context.products[receipt_item.product_id]
            billed = self._positive_qty(line.billed_quantity, f"Line {index} billed quantity")
            invoice_cost = self._nonnegative_money(line.unit_cost, f"Line {index} unit cost")
            quantity_variance = self._variance_percent(receipt_item.received_quantity, billed)
            price_variance = self._variance_percent(order_item.unit_cost, invoice_cost)
            if quantity_variance > context.company.purchase_quantity_tolerance_percent:
                raise ConflictError("Supplier invoice quantity exceeds the configured tolerance.")
            if price_variance > context.company.purchase_price_tolerance_percent:
                raise ConflictError("Supplier invoice price exceeds the configured tolerance.")
            taxable = money(billed * invoice_cost)
            prepared.append(
                (
                    line,
                    receipt_item,
                    order_item,
                    product,
                    billed,
                    invoice_cost,
                    taxable,
                )
            )
            if method == "VALUE":
                weights.append(taxable)
            else:
                if product.unit_weight_kg is None or product.unit_weight_kg <= ZERO_QTY:
                    raise ValidationError(
                        "Weight allocation requires a positive product unit weight."
                    )
                weights.append(qty(product.unit_weight_kg * receipt_item.received_quantity))
        allocations = apportion(landed_total, weights)
        rows: list[PurchaseCostPreviewLine] = []
        for prepared_row, allocation in zip(prepared, allocations, strict=True):
            line, receipt_item, order_item, product, billed, invoice_cost, taxable = prepared_row
            received = qty(receipt_item.received_quantity)
            unit_landed = money(invoice_cost + allocation / received)
            new_average = money(
                (product.on_hand * product.cost_price + received * unit_landed)
                / qty(product.on_hand + received)
            )
            rows.append(
                PurchaseCostPreviewLine(
                    goods_receipt_item_id=line.goods_receipt_item_id,
                    purchase_order_item_id=order_item.id,
                    product_id=product.id,
                    received_quantity=received,
                    billed_quantity=billed,
                    expected_unit_cost=money(order_item.unit_cost),
                    invoice_unit_cost=invoice_cost,
                    quantity_variance_percent=self._variance_percent(received, billed),
                    price_variance_percent=self._variance_percent(
                        order_item.unit_cost, invoice_cost
                    ),
                    landed_cost_amount=allocation,
                    unit_landed_cost=unit_landed,
                    old_average_cost=money(product.cost_price),
                    new_average_cost=new_average,
                    taxable_amount=taxable,
                    tax_amount=money(taxable * order_item.tax_rate / Decimal("100")),
                )
            )
        taxable_total = money(sum((row.taxable_amount for row in rows), ZERO))
        tax_total = money(sum((row.tax_amount for row in rows), ZERO))
        interstate = context.supplier.state_code != context.branch.state_code
        cgst = ZERO if interstate else money(tax_total / 2)
        sgst = ZERO if interstate else money(tax_total - cgst)
        igst = tax_total if interstate else ZERO
        return PurchaseInvoicePreview(
            supplier_id=context.supplier.id,
            purchase_order_id=context.order.id,
            goods_receipt_id=context.receipt.id,
            lines=tuple(rows),
            taxable_amount=taxable_total,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            landed_cost_amount=landed_total,
            total_amount=money(taxable_total + tax_total + landed_total),
        )

    def _receive_batch(
        self,
        *,
        product: Product,
        branch_id: int,
        receipt_item: GoodsReceiptItem,
        unit_landed_cost: Decimal,
        user_id: int,
    ) -> StockBatch | None:
        batch_number = receipt_item.batch_number
        if product.batch_tracking_enabled and not batch_number:
            raise ValidationError("A batch number is required for a batch-tracked product.")
        if not batch_number:
            return None
        batch = self.session.scalar(
            select(StockBatch)
            .where(
                StockBatch.company_id == self.company_id,
                StockBatch.branch_id == branch_id,
                StockBatch.product_id == product.id,
                StockBatch.batch_number == batch_number,
                StockBatch.deleted_at.is_(None),
            )
            .with_for_update()
        )
        received = qty(receipt_item.received_quantity)
        if batch is None:
            batch = StockBatch(
                company_id=self.company_id,
                branch_id=branch_id,
                product_id=product.id,
                batch_number=batch_number,
                mfg_date=receipt_item.mfg_date,
                expiry_date=receipt_item.expiry_date,
                cost_price=unit_landed_cost,
                selling_price=product.selling_price,
                quantity_received=received,
                quantity_available=received,
                created_by=user_id,
            )
            self.session.add(batch)
            self.session.flush()
            return batch
        new_total = qty(batch.quantity_received + received)
        batch.cost_price = money(
            (batch.quantity_received * batch.cost_price + received * unit_landed_cost) / new_total
        )
        batch.quantity_received = new_total
        batch.quantity_available = qty(batch.quantity_available + received)
        batch.row_version += 1
        return batch

    def _post_supplier_movement(
        self,
        *,
        supplier: Supplier,
        txn_date: date,
        txn_type: str,
        reference_type: str,
        reference_id: int | str,
        debit: Decimal,
        credit: Decimal,
        due_date: date | None,
        user_id: int,
        notes: str | None = None,
    ) -> SupplierLedger:
        balance = money(supplier.outstanding_balance + credit - debit)
        if balance < ZERO:
            raise ConflictError("Supplier ledger balance cannot become negative.")
        supplier.outstanding_balance = balance
        supplier.row_version += 1
        movement = SupplierLedger(
            company_id=self.company_id,
            supplier_id=supplier.id,
            txn_date=txn_date,
            txn_type=txn_type,
            reference_type=reference_type,
            reference_id=str(reference_id),
            debit_amount=debit,
            credit_amount=credit,
            balance_after=balance,
            due_date=due_date,
            notes=notes,
            created_by=user_id,
        )
        self.session.add(movement)
        self.session.flush()
        return movement

    def _require_company(self, company_id: int) -> Company:
        company = self.session.scalar(
            select(Company).where(
                Company.id == company_id,
                Company.deleted_at.is_(None),
                Company.is_active.is_(True),
            )
        )
        if company is None or company.id != self.company_id:
            raise EntityNotFoundError("Company was not found.")
        return company

    def _require_branch(self, branch_id: int) -> Branch:
        branch = self.session.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == self.company_id,
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
            )
        )
        if branch is None:
            raise EntityNotFoundError("Branch was not found.")
        return branch

    def _require_supplier(self, supplier_id: int, *, for_update: bool = False) -> Supplier:
        statement = select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.company_id == self.company_id,
            Supplier.deleted_at.is_(None),
            Supplier.is_active.is_(True),
        )
        if for_update:
            statement = statement.with_for_update()
        supplier = self.session.scalar(statement)
        if supplier is None:
            raise EntityNotFoundError("Supplier was not found.")
        return supplier

    def _load_products(
        self, product_ids: set[int], *, for_update: bool = False
    ) -> dict[int, Product]:
        statement = select(Product).where(
            Product.company_id == self.company_id,
            Product.id.in_(sorted(product_ids)),
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
        )
        if for_update:
            statement = statement.order_by(Product.id).with_for_update()
        products = {product.id: product for product in self.session.scalars(statement)}
        if products.keys() != product_ids:
            raise EntityNotFoundError("One or more purchase products were not found.")
        return products

    def _require_command_company(self, company_id: int) -> None:
        if company_id != self.company_id:
            raise ValidationError("Command company does not match the active tenant.")

    @staticmethod
    def _positive_qty(value: object, label: str) -> Decimal:
        try:
            result = qty(to_decimal(value))
        except ValueError as exc:
            raise ValidationError(f"{label} must be numeric.") from exc
        if result <= ZERO_QTY:
            raise ValidationError(f"{label} must be greater than zero.")
        return result

    @staticmethod
    def _nonnegative_money(value: object, label: str) -> Decimal:
        try:
            result = money(value)
        except ValueError as exc:
            raise ValidationError(f"{label} must be numeric.") from exc
        if result < ZERO:
            raise ValidationError(f"{label} cannot be negative.")
        return result

    @classmethod
    def _positive_money(cls, value: object, label: str) -> Decimal:
        result = cls._nonnegative_money(value, label)
        if result <= ZERO:
            raise ValidationError(f"{label} must be greater than zero.")
        return result

    @staticmethod
    def _rate(value: object, label: str) -> Decimal:
        try:
            rate = money(value)
        except ValueError as exc:
            raise ValidationError(f"{label} must be numeric.") from exc
        if rate < ZERO or rate > Decimal("100.00"):
            raise ValidationError(f"{label} must be between 0 and 100.")
        return rate

    @staticmethod
    def _variance_percent(expected: object, actual: object) -> Decimal:
        expected_decimal = to_decimal(expected)
        actual_decimal = to_decimal(actual)
        if expected_decimal == 0:
            return ZERO if actual_decimal == 0 else Decimal("100.00")
        return money(abs(actual_decimal - expected_decimal) * Decimal("100") / expected_decimal)

    @classmethod
    def _enforce_price_tolerance(
        cls, *, expected: Decimal, actual: Decimal, tolerance: Decimal
    ) -> None:
        if cls._variance_percent(expected, actual) > tolerance:
            raise ConflictError("Received price exceeds the configured purchase tolerance.")

    def _audit(self, user_id: int, action: str, entity_type: str, entity_id: int) -> None:
        record_audit_event(
            self.session,
            company_id=self.company_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
        )
