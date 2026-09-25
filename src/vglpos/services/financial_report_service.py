"""Management reports using historical cost and attributable ledger snapshots."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vglpos.domain.enums import SaleStatus
from vglpos.domain.models import (
    CashMovement,
    Category,
    CreditNote,
    CreditNoteItem,
    Customer,
    Product,
    Purchase,
    PurchaseReturn,
    Sale,
    SaleItem,
    SalePayment,
    Shift,
    Supplier,
    SupplierLedger,
)
from vglpos.services.exceptions import ValidationError
from vglpos.utils.money import ZERO, money, qty

ZERO_QTY = Decimal("0.000")
_REPORTABLE_STATUSES = (
    SaleStatus.COMPLETED.value,
    SaleStatus.PARTIALLY_RETURNED.value,
    SaleStatus.RETURNED.value,
)


@dataclass(frozen=True, slots=True)
class GrossMarginRow:
    dimension: str
    key: str
    label: str
    quantity: Decimal
    net_sales: Decimal
    cost_of_goods: Decimal
    gross_margin: Decimal
    margin_percent: Decimal


@dataclass(frozen=True, slots=True)
class DayBookRow:
    transaction_date: date
    document_type: str
    document_number: str
    party: str
    debit_amount: Decimal
    credit_amount: Decimal


@dataclass(frozen=True, slots=True)
class CashBookRow:
    transaction_date: date
    reference: str
    description: str
    cash_in: Decimal
    cash_out: Decimal
    balance: Decimal


@dataclass(frozen=True, slots=True)
class AgeingRow:
    party_id: int
    party_code: str
    party_name: str
    current: Decimal
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    over_90: Decimal
    total: Decimal


@dataclass(frozen=True, slots=True)
class PeriodSummary:
    start_date: date
    end_date: date
    bill_count: int
    quantity: Decimal
    net_sales: Decimal
    gross_margin: Decimal


@dataclass(frozen=True, slots=True)
class SalesComparison:
    current: PeriodSummary
    previous: PeriodSummary
    sales_change: Decimal
    sales_change_percent: Decimal
    margin_change: Decimal


@dataclass(frozen=True, slots=True)
class HourlySalesRow:
    hour: int
    bill_count: int
    quantity: Decimal
    net_sales: Decimal


@dataclass(slots=True)
class _MarginAccumulator:
    quantity: Decimal = ZERO_QTY
    net_sales: Decimal = ZERO
    cost: Decimal = ZERO


class FinancialReportService:
    """Produce tenant-scoped financial views without replacing invoice snapshots."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def gross_margin(
        self,
        start_date: date,
        end_date: date,
        *,
        dimension: str,
        branch_id: int | None = None,
    ) -> tuple[GrossMarginRow, ...]:
        """Group net sales against cost_at_sale, including in-period returns."""
        self._validate_dates(start_date, end_date)
        normalized = dimension.strip().upper()
        if normalized not in {"PRODUCT", "CATEGORY", "BRAND", "SUPPLIER"}:
            raise ValidationError(
                "Gross-margin dimension must be PRODUCT, CATEGORY, BRAND, or SUPPLIER."
            )
        values: dict[tuple[str, str], _MarginAccumulator] = {}
        statement = (
            select(
                SaleItem,
                Product.sku,
                Product.name,
                Product.brand,
                Category.id,
                Category.name,
                Supplier.code,
                Supplier.name,
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.product_id)
            .outerjoin(
                Category,
                (Category.id == Product.category_id)
                & (Category.company_id == self.company_id)
                & Category.deleted_at.is_(None),
            )
            .outerjoin(
                Supplier,
                (Supplier.id == SaleItem.supplier_id_at_sale)
                & (Supplier.company_id == self.company_id)
                & Supplier.deleted_at.is_(None),
            )
            .where(
                Sale.company_id == self.company_id,
                SaleItem.company_id == self.company_id,
                Product.company_id == self.company_id,
                Sale.business_date.between(start_date, end_date),
                Sale.sale_status.in_(_REPORTABLE_STATUSES),
                Sale.deleted_at.is_(None),
                SaleItem.deleted_at.is_(None),
                Product.deleted_at.is_(None),
            )
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        for row in self.session.execute(statement):
            item = row[0]
            key = self._margin_key(normalized, row)
            target = values.setdefault(key, _MarginAccumulator())
            target.quantity = qty(target.quantity + item.quantity)
            target.net_sales = money(target.net_sales + item.taxable_amount)
            target.cost = money(target.cost + item.quantity * item.cost_at_sale)
        return_statement = (
            select(
                CreditNoteItem,
                SaleItem,
                Product.sku,
                Product.name,
                Product.brand,
                Category.id,
                Category.name,
                Supplier.code,
                Supplier.name,
            )
            .join(CreditNote, CreditNote.id == CreditNoteItem.credit_note_id)
            .join(SaleItem, SaleItem.id == CreditNoteItem.original_sale_item_id)
            .join(Product, Product.id == SaleItem.product_id)
            .outerjoin(
                Category,
                (Category.id == Product.category_id)
                & (Category.company_id == self.company_id)
                & Category.deleted_at.is_(None),
            )
            .outerjoin(
                Supplier,
                (Supplier.id == SaleItem.supplier_id_at_sale)
                & (Supplier.company_id == self.company_id)
                & Supplier.deleted_at.is_(None),
            )
            .where(
                CreditNote.company_id == self.company_id,
                CreditNoteItem.company_id == self.company_id,
                SaleItem.company_id == self.company_id,
                Product.company_id == self.company_id,
                CreditNote.note_date.between(start_date, end_date),
                CreditNote.deleted_at.is_(None),
                CreditNoteItem.deleted_at.is_(None),
                SaleItem.deleted_at.is_(None),
                Product.deleted_at.is_(None),
            )
        )
        if branch_id is not None:
            return_statement = return_statement.where(CreditNote.branch_id == branch_id)
        for return_row in self.session.execute(return_statement):
            note_item = return_row[0]
            sale_item = return_row[1]
            key = self._margin_key(normalized, return_row, offset=1)
            target = values.setdefault(key, _MarginAccumulator())
            ratio = note_item.quantity / sale_item.quantity
            target.quantity = qty(target.quantity - note_item.quantity)
            target.net_sales = money(target.net_sales - money(sale_item.taxable_amount * ratio))
            target.cost = money(target.cost - note_item.quantity * sale_item.cost_at_sale)
        return tuple(
            self._margin_row(normalized, key, label, value)
            for (key, label), value in sorted(values.items(), key=lambda item: item[0])
        )

    def day_book(
        self, start_date: date, end_date: date, *, branch_id: int | None = None
    ) -> tuple[DayBookRow, ...]:
        """List sales, notes, purchases, returns, and supplier payments chronologically."""
        self._validate_dates(start_date, end_date)
        rows: list[DayBookRow] = []
        sales = (
            select(Sale, Customer.name)
            .outerjoin(
                Customer,
                (Customer.id == Sale.customer_id) & (Customer.company_id == self.company_id),
            )
            .where(
                Sale.company_id == self.company_id,
                Sale.business_date.between(start_date, end_date),
                Sale.sale_status.in_(_REPORTABLE_STATUSES),
                Sale.deleted_at.is_(None),
            )
        )
        notes = select(CreditNote).where(
            CreditNote.company_id == self.company_id,
            CreditNote.note_date.between(start_date, end_date),
            CreditNote.deleted_at.is_(None),
        )
        purchases = (
            select(Purchase, Supplier.name)
            .join(Supplier, Supplier.id == Purchase.supplier_id)
            .where(
                Purchase.company_id == self.company_id,
                Supplier.company_id == self.company_id,
                Purchase.invoice_date.between(start_date, end_date),
                Purchase.deleted_at.is_(None),
                Supplier.deleted_at.is_(None),
            )
        )
        returns = (
            select(PurchaseReturn, Supplier.name)
            .join(Supplier, Supplier.id == PurchaseReturn.supplier_id)
            .where(
                PurchaseReturn.company_id == self.company_id,
                Supplier.company_id == self.company_id,
                PurchaseReturn.return_date.between(start_date, end_date),
                PurchaseReturn.deleted_at.is_(None),
                Supplier.deleted_at.is_(None),
            )
        )
        if branch_id is not None:
            sales = sales.where(Sale.branch_id == branch_id)
            notes = notes.where(CreditNote.branch_id == branch_id)
            purchases = purchases.where(Purchase.branch_id == branch_id)
            returns = returns.where(PurchaseReturn.branch_id == branch_id)
        for sale, customer_name in self.session.execute(sales):
            rows.append(
                DayBookRow(
                    sale.business_date,
                    "SALE",
                    sale.invoice_number,
                    sale.customer_name_at_sale or customer_name or "Cash",
                    money(sale.net_amount),
                    ZERO,
                )
            )
        for note in self.session.scalars(notes):
            rows.append(
                DayBookRow(
                    note.note_date,
                    "CREDIT_NOTE",
                    note.credit_note_number,
                    "Customer returns",
                    ZERO,
                    money(note.net_amount),
                )
            )
        for purchase, supplier_name in self.session.execute(purchases):
            rows.append(
                DayBookRow(
                    purchase.invoice_date,
                    "PURCHASE",
                    purchase.invoice_number,
                    supplier_name,
                    ZERO,
                    money(purchase.total_amount),
                )
            )
        for purchase_return, supplier_name in self.session.execute(returns):
            rows.append(
                DayBookRow(
                    purchase_return.return_date,
                    "PURCHASE_RETURN",
                    purchase_return.debit_note_number,
                    supplier_name,
                    money(purchase_return.total_amount),
                    ZERO,
                )
            )
        payments = (
            select(SupplierLedger, Supplier.name)
            .join(Supplier, Supplier.id == SupplierLedger.supplier_id)
            .where(
                SupplierLedger.company_id == self.company_id,
                Supplier.company_id == self.company_id,
                SupplierLedger.txn_date.between(start_date, end_date),
                SupplierLedger.txn_type == "PAYMENT",
                SupplierLedger.deleted_at.is_(None),
                Supplier.deleted_at.is_(None),
            )
        )
        for movement, supplier_name in self.session.execute(payments):
            rows.append(
                DayBookRow(
                    movement.txn_date,
                    "SUPPLIER_PAYMENT",
                    movement.reference_id,
                    supplier_name,
                    money(movement.debit_amount),
                    ZERO,
                )
            )
        return tuple(
            sorted(
                rows, key=lambda row: (row.transaction_date, row.document_type, row.document_number)
            )
        )

    def cash_book(
        self, start_date: date, end_date: date, *, branch_id: int | None = None
    ) -> tuple[CashBookRow, ...]:
        """Build a running cash balance from cash tenders and drawer movements."""
        self._validate_dates(start_date, end_date)
        entries: list[tuple[date, str, str, Decimal, Decimal]] = []
        payments = (
            select(Sale.business_date, Sale.invoice_number, SalePayment.amount)
            .join(SalePayment, SalePayment.sale_id == Sale.id)
            .where(
                Sale.company_id == self.company_id,
                SalePayment.company_id == self.company_id,
                Sale.business_date.between(start_date, end_date),
                Sale.sale_status.in_(_REPORTABLE_STATUSES),
                SalePayment.payment_method == "CASH",
                Sale.deleted_at.is_(None),
                SalePayment.deleted_at.is_(None),
            )
        )
        if branch_id is not None:
            payments = payments.where(Sale.branch_id == branch_id)
        for business_date, invoice_number, amount in self.session.execute(payments):
            entries.append((business_date, invoice_number, "Cash sale", money(amount), ZERO))
        movements = (
            select(CashMovement, Shift.branch_id)
            .join(Shift, Shift.id == CashMovement.shift_id)
            .where(
                CashMovement.company_id == self.company_id,
                Shift.company_id == self.company_id,
                func.date(CashMovement.created_at).between(start_date, end_date),
                CashMovement.deleted_at.is_(None),
                Shift.deleted_at.is_(None),
            )
        )
        if branch_id is not None:
            movements = movements.where(Shift.branch_id == branch_id)
        for movement, _movement_branch in self.session.execute(movements):
            incoming = movement.movement_type in {"PAY_IN", "FLOAT_ADD"}
            entries.append(
                (
                    movement.created_at.date(),
                    f"CASH-{movement.id}",
                    f"{movement.movement_type}: {movement.reason}",
                    money(movement.amount) if incoming else ZERO,
                    ZERO if incoming else money(movement.amount),
                )
            )
        balance = ZERO
        rows = []
        for transaction_date, reference, description, cash_in, cash_out in sorted(entries):
            balance = money(balance + cash_in - cash_out)
            rows.append(
                CashBookRow(transaction_date, reference, description, cash_in, cash_out, balance)
            )
        return tuple(rows)

    def customer_ageing(self, *, as_of: date) -> tuple[AgeingRow, ...]:
        """Age customer credit balances after applying reductions oldest-first."""
        customers = tuple(
            self.session.scalars(
                select(Customer).where(
                    Customer.company_id == self.company_id,
                    Customer.outstanding_balance > ZERO,
                    Customer.deleted_at.is_(None),
                    Customer.is_active.is_(True),
                )
            )
        )
        rows = []
        for customer in customers:
            invoices: list[tuple[date, Decimal]] = [
                (business_date, money(amount))
                for business_date, amount in self.session.execute(
                    select(
                        Sale.business_date,
                        func.sum(SalePayment.amount),
                    )
                    .join(SalePayment, SalePayment.sale_id == Sale.id)
                    .where(
                        Sale.company_id == self.company_id,
                        SalePayment.company_id == self.company_id,
                        Sale.customer_id == customer.id,
                        Sale.business_date <= as_of,
                        SalePayment.payment_method == "CREDIT",
                        Sale.sale_status.in_(_REPORTABLE_STATUSES),
                        Sale.deleted_at.is_(None),
                        SalePayment.deleted_at.is_(None),
                    )
                    .group_by(Sale.id, Sale.business_date)
                    .order_by(Sale.business_date, Sale.id)
                )
            ]
            derived = money(sum((amount for _date, amount in invoices), ZERO))
            reduction = money(max(ZERO, derived - customer.outstanding_balance))
            invoices = self._apply_fifo_reduction(invoices, reduction)
            buckets = self._buckets(invoices, as_of)
            rows.append(
                AgeingRow(
                    customer.id,
                    customer.phone,
                    customer.name,
                    *buckets,
                )
            )
        return tuple(sorted(rows, key=lambda row: row.party_name))

    def supplier_ageing(self, *, as_of: date) -> tuple[AgeingRow, ...]:
        """Age invoice credits after allocating supplier debits oldest-first."""
        suppliers = tuple(
            self.session.scalars(
                select(Supplier).where(
                    Supplier.company_id == self.company_id,
                    Supplier.outstanding_balance > ZERO,
                    Supplier.deleted_at.is_(None),
                    Supplier.is_active.is_(True),
                )
            )
        )
        rows = []
        for supplier in suppliers:
            movements = tuple(
                self.session.scalars(
                    select(SupplierLedger)
                    .where(
                        SupplierLedger.company_id == self.company_id,
                        SupplierLedger.supplier_id == supplier.id,
                        SupplierLedger.txn_date <= as_of,
                        SupplierLedger.deleted_at.is_(None),
                    )
                    .order_by(SupplierLedger.txn_date, SupplierLedger.id)
                )
            )
            invoices: list[tuple[date, Decimal]] = [
                (movement.due_date or movement.txn_date, money(movement.credit_amount))
                for movement in movements
                if movement.credit_amount > ZERO
            ]
            debits = money(sum((movement.debit_amount for movement in movements), ZERO))
            invoices = self._apply_fifo_reduction(invoices, debits)
            buckets = self._buckets(invoices, as_of)
            rows.append(AgeingRow(supplier.id, supplier.code, supplier.name, *buckets))
        return tuple(sorted(rows, key=lambda row: row.party_name))

    def sales_comparison(
        self,
        current_start: date,
        current_end: date,
        previous_start: date,
        previous_end: date,
        *,
        branch_id: int | None = None,
    ) -> SalesComparison:
        """Compare equivalent caller-selected periods without hidden date shifting."""
        current = self._period_summary(current_start, current_end, branch_id)
        previous = self._period_summary(previous_start, previous_end, branch_id)
        change = money(current.net_sales - previous.net_sales)
        change_percent = (
            ZERO
            if previous.net_sales == ZERO
            else money(change * Decimal("100") / previous.net_sales)
        )
        return SalesComparison(
            current=current,
            previous=previous,
            sales_change=change,
            sales_change_percent=change_percent,
            margin_change=money(current.gross_margin - previous.gross_margin),
        )

    def hourly_sales(
        self, start_date: date, end_date: date, *, branch_id: int | None = None
    ) -> tuple[HourlySalesRow, ...]:
        """Aggregate bills and units by local invoice creation hour for staffing."""
        self._validate_dates(start_date, end_date)
        statement = (
            select(
                Sale.id,
                Sale.created_at,
                Sale.net_amount,
                func.coalesce(func.sum(SaleItem.quantity), ZERO_QTY),
            )
            .join(SaleItem, SaleItem.sale_id == Sale.id)
            .where(
                Sale.company_id == self.company_id,
                SaleItem.company_id == self.company_id,
                Sale.business_date.between(start_date, end_date),
                Sale.sale_status.in_(_REPORTABLE_STATUSES),
                Sale.deleted_at.is_(None),
                SaleItem.deleted_at.is_(None),
            )
            .group_by(Sale.id)
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        values: dict[int, tuple[int, Decimal, Decimal]] = dict.fromkeys(
            range(24), (0, ZERO_QTY, ZERO)
        )
        for _sale_id, created_at, net_amount, quantity in self.session.execute(statement):
            bill_count, units, net_sales = values[created_at.hour]
            values[created_at.hour] = (
                bill_count + 1,
                qty(units + quantity),
                money(net_sales + net_amount),
            )
        return tuple(
            HourlySalesRow(hour, value[0], qty(value[1]), money(value[2]))
            for hour, value in values.items()
        )

    def _period_summary(
        self, start_date: date, end_date: date, branch_id: int | None
    ) -> PeriodSummary:
        self._validate_dates(start_date, end_date)
        bill_statement = select(func.count(Sale.id)).where(
            Sale.company_id == self.company_id,
            Sale.business_date.between(start_date, end_date),
            Sale.sale_status.in_(_REPORTABLE_STATUSES),
            Sale.deleted_at.is_(None),
        )
        if branch_id is not None:
            bill_statement = bill_statement.where(Sale.branch_id == branch_id)
        bill_count = int(self.session.scalar(bill_statement) or 0)
        margin_rows = self.gross_margin(
            start_date,
            end_date,
            dimension="PRODUCT",
            branch_id=branch_id,
        )
        return PeriodSummary(
            start_date,
            end_date,
            bill_count,
            qty(sum((row.quantity for row in margin_rows), ZERO_QTY)),
            money(sum((row.net_sales for row in margin_rows), ZERO)),
            money(sum((row.gross_margin for row in margin_rows), ZERO)),
        )

    @staticmethod
    def _margin_key(dimension: str, row: Sequence[object], *, offset: int = 0) -> tuple[str, str]:
        values = tuple(row)
        if dimension == "PRODUCT":
            return str(values[offset + 1]), str(values[offset + 2])
        if dimension == "CATEGORY":
            return (
                str(values[offset + 4] or "UNASSIGNED"),
                str(values[offset + 5] or "Unassigned"),
            )
        if dimension == "BRAND":
            label = str(values[offset + 3] or "Unassigned")
            return label.upper(), label
        return (
            str(values[offset + 6] or "UNASSIGNED"),
            str(values[offset + 7] or "Unassigned"),
        )

    @staticmethod
    def _margin_row(
        dimension: str, key: str, label: str, value: _MarginAccumulator
    ) -> GrossMarginRow:
        margin = money(value.net_sales - value.cost)
        percent = (
            ZERO if value.net_sales == ZERO else money(margin * Decimal("100") / value.net_sales)
        )
        return GrossMarginRow(
            dimension,
            key,
            label,
            qty(value.quantity),
            money(value.net_sales),
            money(value.cost),
            margin,
            percent,
        )

    @staticmethod
    def _apply_fifo_reduction(
        invoices: list[tuple[date, Decimal]], reduction: Decimal
    ) -> list[tuple[date, Decimal]]:
        remaining = reduction
        reduced = []
        for due_date, raw_amount in invoices:
            amount = money(raw_amount)
            if remaining <= ZERO:
                reduced.append((due_date, amount))
                continue
            applied = min(amount, remaining)
            reduced.append((due_date, money(amount - applied)))
            remaining = money(remaining - applied)
        return reduced

    @staticmethod
    def _buckets(
        values: Iterable[tuple[date, Decimal]], as_of: date
    ) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
        buckets = [ZERO, ZERO, ZERO, ZERO, ZERO]
        for due_date, raw_amount in values:
            amount = money(raw_amount)
            if amount <= ZERO:
                continue
            age = (as_of - due_date).days
            index = 0 if age <= 0 else 1 if age <= 30 else 2 if age <= 60 else 3 if age <= 90 else 4
            buckets[index] = money(buckets[index] + amount)
        total = money(sum(buckets, ZERO))
        return (buckets[0], buckets[1], buckets[2], buckets[3], buckets[4], total)

    @staticmethod
    def _validate_dates(start_date: date, end_date: date) -> None:
        if start_date > end_date:
            raise ValidationError("Report start date cannot be after end date.")
