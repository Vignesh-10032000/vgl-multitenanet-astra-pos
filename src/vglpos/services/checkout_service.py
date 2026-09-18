"""Transactional sale checkout orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.enums import DocType, PaymentMethod, SupplyType
from vglpos.domain.models import (
    Branch,
    Customer,
    Product,
    Sale,
    SaleItem,
    SalePayment,
    Shift,
    TaxRate,
    Terminal,
    User,
)
from vglpos.repositories import SaleRepository
from vglpos.services.exceptions import (
    CheckoutError,
    EntityNotFoundError,
    InsufficientStockError,
    InvalidPaymentError,
    ServiceError,
    ValidationError,
)
from vglpos.services.inventory_service import InventoryService
from vglpos.services.invoice_number_service import InvoiceNumberService
from vglpos.services.tax_engine import TaxEngine, TaxLineInput, TaxResult
from vglpos.utils.gst import state_code_from_gstin
from vglpos.utils.money import ZERO, money, qty, to_decimal

logger = logging.getLogger(__name__)
LOYALTY_EARN_DIVISOR = Decimal("10.00")


@dataclass(frozen=True, slots=True)
class CheckoutLineCommand:
    """Identify a requested product and quantity while treating catalogue facts as untrusted."""

    product_id: int
    quantity: object
    line_discount: object = ZERO
    client_unit_price: object | None = None
    client_tax_rate: object | None = None


@dataclass(frozen=True, slots=True)
class PaymentCommand:
    """Represent one tender component supplied by a checkout route."""

    method: str
    amount: object
    reference_number: str | None = None


@dataclass(frozen=True, slots=True)
class CheckoutCommand:
    """Carry authenticated checkout facts from a route into the service layer."""

    company_id: int
    branch_id: int
    terminal_id: int
    cashier_id: int
    lines: tuple[CheckoutLineCommand, ...] | list[CheckoutLineCommand]
    payments: tuple[PaymentCommand, ...] | list[PaymentCommand] = field(default_factory=tuple)
    customer_id: int | None = None
    shift_id: int | None = None
    offline_uuid: str | None = None
    business_date: date = field(default_factory=date.today)
    order_discount: object = ZERO
    apply_round_off: bool = True
    amount_paid: object | None = None
    payment_method: str | None = None
    notes: str | None = None
    client_total: object | None = None


class CheckoutService:
    """Persist a fully server-priced sale as one atomic transaction."""

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

    def checkout(self, cmd: CheckoutCommand) -> Sale:
        """Commit exactly once; every failure rolls back numbering, stock, and customer state."""
        if not cmd.company_id:
            raise ValidationError("Company is required for checkout.")
        if cmd.offline_uuid:
            existing = SaleRepository(self.session, cmd.company_id).find_by_offline_uuid(
                cmd.offline_uuid
            )
            if existing is not None:
                return existing
        try:
            sale = self._build_checkout(cmd)
            self.session.commit()
            self.session.refresh(sale)
            return sale
        except IntegrityError as exc:
            self.session.rollback()
            if cmd.offline_uuid:
                existing = SaleRepository(self.session, cmd.company_id).find_by_offline_uuid(
                    cmd.offline_uuid
                )
                if existing is not None:
                    return existing
            logger.exception(
                "Checkout persistence conflict",
                extra={"company_id": cmd.company_id, "offline_uuid": cmd.offline_uuid},
            )
            raise CheckoutError("Checkout conflicted with another transaction.") from exc
        except ServiceError:
            self.session.rollback()
            raise
        except ValueError as exc:
            self.session.rollback()
            raise ValidationError(str(exc)) from exc

    def _build_checkout(self, cmd: CheckoutCommand) -> Sale:
        if not 1 <= len(cmd.lines) <= 200:
            raise ValidationError("Checkout must contain between 1 and 200 lines.")
        branch = self._require_context(cmd)
        requested = self._aggregate_quantities(cmd.lines)
        products = self._lock_products(cmd.company_id, tuple(requested))
        self._check_stock(products, requested)
        rates = self._load_rates(cmd.company_id, products, cmd.business_date)
        customer = self._load_customer(cmd.company_id, cmd.customer_id)
        place_of_supply = (
            state_code_from_gstin(customer.gstin)
            if customer is not None and customer.gstin is not None
            else branch.state_code
        )

        tax_lines = [
            TaxLineInput(
                quantity=line.quantity,
                unit_price=products[line.product_id].selling_price,
                tax_rate=rates[products[line.product_id].tax_rate_id].rate,
                cess_rate=rates[products[line.product_id].tax_rate_id].cess_rate,
                line_discount=line.line_discount,
                tax_inclusive=products[line.product_id].is_tax_inclusive,
            )
            for line in cmd.lines
        ]
        result = TaxEngine.compute(
            tax_lines,
            supplier_state=branch.state_code,
            place_of_supply=place_of_supply,
            order_discount=to_decimal(cmd.order_discount),
            apply_round_off=cmd.apply_round_off,
        )
        payments = self._payments(cmd, result)
        document_no, _ = InvoiceNumberService(self.session).allocate(
            cmd.company_id,
            cmd.branch_id,
            cmd.terminal_id,
            DocType.SALE.value,
            cmd.business_date,
        )
        amount_paid = money(sum((amount for _, amount, _ in payments), ZERO))
        sale = Sale(
            company_id=cmd.company_id,
            branch_id=cmd.branch_id,
            terminal_id=cmd.terminal_id,
            customer_id=cmd.customer_id,
            cashier_id=cmd.cashier_id,
            shift_id=cmd.shift_id,
            offline_uuid=cmd.offline_uuid,
            invoice_number=document_no,
            business_date=cmd.business_date,
            sale_status="COMPLETED",
            supply_type=(
                SupplyType.INTERSTATE.value if result.is_interstate else SupplyType.INTRASTATE.value
            ),
            gross_amount=result.gross_amount,
            discount_amount=result.discount_amount,
            taxable_amount=result.taxable_amount,
            cgst_amount=result.cgst_amount,
            sgst_amount=result.sgst_amount,
            igst_amount=result.igst_amount,
            cess_amount=result.cess_amount,
            round_off=result.round_off,
            net_amount=result.net_amount,
            amount_paid=amount_paid,
            balance_due=ZERO,
            payment_method=payments[0][0] if len(payments) == 1 else "SPLIT",
            notes=cmd.notes,
            created_by=cmd.cashier_id,
        )
        self.session.add(sale)
        self.session.flush()
        self._add_sale_lines(cmd, sale, products, result)
        self._add_payments(cmd, sale, payments)

        inventory = InventoryService(self.session, cmd.company_id)
        for product_id in sorted(requested):
            product = products[product_id]
            if product.is_inventory_tracked:
                inventory.record_movement(
                    product,
                    cmd.branch_id,
                    -requested[product_id],
                    "SALE",
                    "sales",
                    sale.id,
                    cmd.cashier_id,
                )
        if customer is not None:
            earned_points = qty(result.net_amount / self.loyalty_earn_divisor)
            self.session.execute(
                update(Customer)
                .where(
                    Customer.id == customer.id,
                    Customer.company_id == cmd.company_id,
                    Customer.deleted_at.is_(None),
                )
                .values(
                    loyalty_points=Customer.loyalty_points + earned_points,
                    total_spent=Customer.total_spent + result.net_amount,
                    total_orders=Customer.total_orders + 1,
                    row_version=Customer.row_version + 1,
                )
            )
        self.session.flush()
        return sale

    def _require_context(self, cmd: CheckoutCommand) -> Branch:
        branch = self.session.scalar(
            select(Branch).where(
                Branch.id == cmd.branch_id,
                Branch.company_id == cmd.company_id,
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
            )
        )
        if branch is None:
            raise EntityNotFoundError("Branch was not found.")
        terminal = self.session.scalar(
            select(Terminal.id).where(
                Terminal.id == cmd.terminal_id,
                Terminal.company_id == cmd.company_id,
                Terminal.branch_id == cmd.branch_id,
                Terminal.deleted_at.is_(None),
                Terminal.is_active.is_(True),
            )
        )
        if terminal is None:
            raise EntityNotFoundError("Terminal was not found.")
        cashier = self.session.scalar(
            select(User.id).where(
                User.id == cmd.cashier_id,
                User.company_id == cmd.company_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        if cashier is None:
            raise EntityNotFoundError("Cashier was not found.")
        if cmd.shift_id is not None:
            shift = self.session.scalar(
                select(Shift.id).where(
                    Shift.id == cmd.shift_id,
                    Shift.company_id == cmd.company_id,
                    Shift.branch_id == cmd.branch_id,
                    Shift.terminal_id == cmd.terminal_id,
                    Shift.cashier_id == cmd.cashier_id,
                    Shift.status == "OPEN",
                    Shift.deleted_at.is_(None),
                )
            )
            if shift is None:
                raise EntityNotFoundError("Open shift was not found.")
        return branch

    @staticmethod
    def _aggregate_quantities(
        lines: tuple[CheckoutLineCommand, ...] | list[CheckoutLineCommand],
    ) -> dict[int, Decimal]:
        quantities: dict[int, Decimal] = {}
        for index, line in enumerate(lines, start=1):
            if not line.product_id:
                raise ValidationError(f"Line {index} product is required.")
            try:
                quantity = qty(to_decimal(line.quantity))
            except ValueError as exc:
                raise ValidationError(f"Line {index} quantity must be numeric.") from exc
            if quantity <= ZERO:
                raise ValidationError(f"Line {index} quantity must be greater than zero.")
            quantities[line.product_id] = qty(
                quantities.get(line.product_id, Decimal("0.000")) + quantity
            )
        return quantities

    def _lock_products(self, company_id: int, product_ids: tuple[int, ...]) -> dict[int, Product]:
        statement = (
            select(Product)
            .where(
                Product.company_id == company_id,
                Product.id.in_(sorted(product_ids)),
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
            .order_by(Product.id)
            .with_for_update()
        )
        products = {product.id: product for product in self.session.scalars(statement)}
        missing = sorted(set(product_ids) - products.keys())
        if missing:
            raise EntityNotFoundError(f"Products were not found: {missing}.")
        return products

    @staticmethod
    def _check_stock(products: dict[int, Product], requested: dict[int, Decimal]) -> None:
        for product_id in sorted(requested):
            product = products[product_id]
            available = qty(product.on_hand - product.reserved_quantity)
            if (
                product.is_inventory_tracked
                and not product.allow_negative_stock
                and available < requested[product_id]
            ):
                raise InsufficientStockError(
                    f"Insufficient stock for product {product_id}; "
                    f"available {available}, requested {requested[product_id]}."
                )

    def _load_rates(
        self,
        company_id: int,
        products: dict[int, Product],
        on_date: date,
    ) -> dict[int, TaxRate]:
        rate_ids = {product.tax_rate_id for product in products.values()}
        statement = select(TaxRate).where(
            TaxRate.id.in_(rate_ids),
            TaxRate.company_id == company_id,
            TaxRate.deleted_at.is_(None),
            TaxRate.effective_from <= on_date,
            (TaxRate.effective_to.is_(None) | (TaxRate.effective_to >= on_date)),
        )
        rates = {rate.id: rate for rate in self.session.scalars(statement)}
        if set(rate_ids) != rates.keys():
            raise EntityNotFoundError("An effective product tax rate was not found.")
        return rates

    def _load_customer(self, company_id: int, customer_id: int | None) -> Customer | None:
        if customer_id is None:
            return None
        customer = self.session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.company_id == company_id,
                Customer.deleted_at.is_(None),
                Customer.is_active.is_(True),
            )
        )
        if customer is None:
            raise EntityNotFoundError("Customer was not found.")
        return customer

    def _payments(
        self, cmd: CheckoutCommand, result: TaxResult
    ) -> tuple[tuple[str, Decimal, str | None], ...]:
        raw_payments = list(cmd.payments)
        if not raw_payments and cmd.amount_paid is not None and cmd.payment_method is not None:
            raw_payments = [PaymentCommand(cmd.payment_method, cmd.amount_paid)]
        if not raw_payments:
            raise InvalidPaymentError("At least one payment is required.")

        valid_methods = {method.value for method in PaymentMethod}
        normalized: list[tuple[str, Decimal, str | None]] = []
        for payment in raw_payments:
            method = str(payment.method).upper()
            if method not in valid_methods:
                raise InvalidPaymentError(f"Unsupported payment method: {payment.method}.")
            try:
                amount = money(payment.amount)
            except ValueError as exc:
                raise InvalidPaymentError("Payment amount must be numeric.") from exc
            if amount <= ZERO:
                raise InvalidPaymentError("Payment amount must be greater than zero.")
            normalized.append((method, amount, payment.reference_number))
        tendered = money(sum((payment[1] for payment in normalized), ZERO))
        if tendered < result.net_amount:
            raise InvalidPaymentError("Tendered amount is less than the payable amount.")
        change = money(tendered - result.net_amount)
        cash_tendered = money(
            sum((amount for method, amount, _ in normalized if method == "CASH"), ZERO)
        )
        if change > cash_tendered:
            raise InvalidPaymentError("Change cannot be funded by a non-cash payment.")
        return tuple(normalized)

    def _add_sale_lines(
        self,
        cmd: CheckoutCommand,
        sale: Sale,
        products: dict[int, Product],
        result: TaxResult,
    ) -> None:
        for line_number, (command_line, calculated) in enumerate(
            zip(cmd.lines, result.lines, strict=True), start=1
        ):
            half_rate = money(calculated.tax_rate / 2)
            item = SaleItem(
                company_id=cmd.company_id,
                sale_id=sale.id,
                product_id=products[command_line.product_id].id,
                line_number=line_number,
                quantity=calculated.quantity,
                unit_price=calculated.unit_price,
                gross_amount=calculated.gross_amount,
                discount_amount=calculated.discount_amount,
                taxable_amount=calculated.taxable_amount,
                tax_rate=calculated.tax_rate,
                cgst_rate=ZERO if result.is_interstate else half_rate,
                sgst_rate=ZERO if result.is_interstate else half_rate,
                igst_rate=calculated.tax_rate if result.is_interstate else ZERO,
                cess_rate=calculated.cess_rate,
                cgst_amount=calculated.cgst_amount,
                sgst_amount=calculated.sgst_amount,
                igst_amount=calculated.igst_amount,
                cess_amount=calculated.cess_amount,
                total_amount=calculated.line_total,
                created_by=cmd.cashier_id,
            )
            self.session.add(item)

    def _add_payments(
        self,
        cmd: CheckoutCommand,
        sale: Sale,
        payments: tuple[tuple[str, Decimal, str | None], ...],
    ) -> None:
        for method, amount, reference in payments:
            self.session.add(
                SalePayment(
                    company_id=cmd.company_id,
                    sale_id=sale.id,
                    payment_method=method,
                    amount=amount,
                    reference_number=reference,
                    created_by=cmd.cashier_id,
                )
            )
