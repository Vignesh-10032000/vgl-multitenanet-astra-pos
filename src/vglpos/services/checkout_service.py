"""Transactional sale checkout orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from vglpos.domain.enums import DocType, PaymentMethod, SupplyType
from vglpos.domain.events import SaleCompleted
from vglpos.domain.models import (
    Branch,
    Company,
    Customer,
    HsnCode,
    LoyaltyLedger,
    Product,
    Sale,
    SaleItem,
    SalePayment,
    Shift,
    TaxRate,
    Terminal,
    User,
)
from vglpos.observability import CHECKOUT_FAILURES, record_checkout_success
from vglpos.repositories import SaleRepository
from vglpos.services.event_dispatcher import publish_event
from vglpos.services.exceptions import (
    CheckoutError,
    EntityNotFoundError,
    InsufficientStockError,
    InvalidPaymentError,
    ServiceError,
    ValidationError,
)
from vglpos.services.inventory_depth_service import InventoryDepthService
from vglpos.services.inventory_service import InventoryService
from vglpos.services.invoice_compliance_service import InvoiceComplianceService
from vglpos.services.invoice_number_service import InvoiceNumberService
from vglpos.services.tax_engine import TaxEngine, TaxLineInput, TaxResult
from vglpos.utils.gst import state_code_from_gstin, uqc_code
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
class NormalizedPayment:
    """Carry one validated tender and any server-derived loyalty quantity."""

    method: str
    amount: Decimal
    reference_number: str | None
    loyalty_points: Decimal | None = None


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


@dataclass(frozen=True, slots=True)
class QuoteCommand:
    """Carry a server-priced cart without payment or persistence facts."""

    company_id: int
    branch_id: int
    lines: tuple[CheckoutLineCommand, ...] | list[CheckoutLineCommand]
    customer_id: int | None = None
    business_date: date = field(default_factory=date.today)
    order_discount: object = ZERO
    apply_round_off: bool = True


@dataclass(frozen=True, slots=True)
class PaymentPreview:
    """Server-authoritative quote and tender balance without persistence."""

    quote: TaxResult
    amount_received: Decimal
    change_due: Decimal
    balance_due: Decimal


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
            record_checkout_success((sale.net_amount,))
            publish_event(
                SaleCompleted(
                    company_id=cmd.company_id,
                    branch_id=cmd.branch_id,
                    sale_id=sale.id,
                    occurred_at=datetime.now(UTC),
                )
            )
            return sale
        except IntegrityError as exc:
            self.session.rollback()
            if cmd.offline_uuid:
                existing = SaleRepository(self.session, cmd.company_id).find_by_offline_uuid(
                    cmd.offline_uuid
                )
                if existing is not None:
                    return existing
            CHECKOUT_FAILURES.labels("persistence_conflict").inc()
            logger.exception(
                "Checkout persistence conflict",
                extra={"company_id": cmd.company_id, "offline_uuid": cmd.offline_uuid},
            )
            raise CheckoutError("Checkout conflicted with another transaction.") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            CHECKOUT_FAILURES.labels("database_unavailable").inc()
            logger.exception("Checkout database failure", extra={"company_id": cmd.company_id})
            raise CheckoutError(
                "Checkout is temporarily unavailable; no sale was committed."
            ) from exc
        except ServiceError as exc:
            self.session.rollback()
            CHECKOUT_FAILURES.labels(exc.error_type).inc()
            raise
        except ValueError as exc:
            self.session.rollback()
            CHECKOUT_FAILURES.labels("validation_error").inc()
            raise ValidationError(str(exc)) from exc

    def checkout_batch(
        self, commands: tuple[CheckoutCommand, ...] | list[CheckoutCommand]
    ) -> tuple[Sale, ...]:
        """Commit an offline batch once so one invalid sale rolls back the entire push."""
        if not 1 <= len(commands) <= 100:
            raise ValidationError("Offline push must contain between 1 and 100 sales.")
        identifiers = [command.offline_uuid for command in commands]
        if any(identifier is None for identifier in identifiers):
            raise ValidationError("Every offline sale requires offline_uuid.")
        if len(set(identifiers)) != len(identifiers):
            raise ValidationError("Offline batch contains duplicate offline_uuid values.")
        sales: list[Sale] = []
        completed_events: list[SaleCompleted] = []
        try:
            for command in commands:
                assert command.offline_uuid is not None
                existing = SaleRepository(self.session, command.company_id).find_by_offline_uuid(
                    command.offline_uuid
                )
                if existing is not None:
                    sales.append(existing)
                else:
                    sale = self._build_checkout(command)
                    sales.append(sale)
                    completed_events.append(
                        SaleCompleted(
                            company_id=command.company_id,
                            branch_id=command.branch_id,
                            sale_id=sale.id,
                            occurred_at=datetime.now(UTC),
                        )
                    )
            self.session.commit()
            for sale in sales:
                self.session.refresh(sale)
            committed_ids = {event.sale_id for event in completed_events}
            record_checkout_success(sale.net_amount for sale in sales if sale.id in committed_ids)
            for event in completed_events:
                publish_event(event)
            return tuple(sales)
        except IntegrityError as exc:
            self.session.rollback()
            CHECKOUT_FAILURES.labels("offline_persistence_conflict").inc()
            raise CheckoutError("Offline batch conflicted with another transaction.") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            CHECKOUT_FAILURES.labels("database_unavailable").inc()
            logger.exception("Offline checkout database failure")
            raise CheckoutError("Offline checkout is temporarily unavailable.") from exc
        except ServiceError as exc:
            self.session.rollback()
            CHECKOUT_FAILURES.labels(exc.error_type).inc()
            raise
        except ValueError as exc:
            self.session.rollback()
            CHECKOUT_FAILURES.labels("validation_error").inc()
            raise ValidationError(str(exc)) from exc

    def quote(self, cmd: QuoteCommand) -> TaxResult:
        """Compute authoritative cart totals without flushing or committing any state."""
        if not cmd.company_id or not 1 <= len(cmd.lines) <= 200:
            raise ValidationError("Quote requires a company and between 1 and 200 lines.")
        branch = self._require_branch(cmd.company_id, cmd.branch_id)
        requested = self._aggregate_quantities(cmd.lines)
        products = self._load_products(cmd.company_id, tuple(requested), for_update=False)
        self._check_stock(products, requested)
        inventory_depth = InventoryDepthService(self.session, cmd.company_id)
        company = self._load_company(cmd.company_id)
        for product_id, required in requested.items():
            product = products[product_id]
            if product.batch_tracking_enabled:
                inventory_depth.ensure_fefo_availability(
                    product=product,
                    branch_id=cmd.branch_id,
                    quantity=required,
                    on_date=cmd.business_date,
                    expired_policy=company.expired_stock_policy,
                )
        rates = self._load_rates(cmd.company_id, products, cmd.business_date)
        customer = self._load_customer(cmd.company_id, cmd.customer_id, for_update=False)
        place_of_supply = branch.state_code
        if customer is not None:
            place_of_supply = (
                state_code_from_gstin(customer.gstin)
                if customer.gstin is not None
                else customer.state_code
            )
        lines = [
            TaxLineInput(
                quantity=line.quantity,
                unit_price=products[line.product_id].selling_price,
                tax_rate=(
                    ZERO
                    if company.composition_scheme_enabled
                    else rates[products[line.product_id].tax_rate_id].rate
                ),
                cess_rate=(
                    ZERO
                    if company.composition_scheme_enabled
                    else rates[products[line.product_id].tax_rate_id].cess_rate
                ),
                line_discount=line.line_discount,
                tax_inclusive=(
                    False
                    if company.composition_scheme_enabled
                    else products[line.product_id].is_tax_inclusive
                ),
            )
            for line in cmd.lines
        ]
        return TaxEngine.compute(
            lines,
            supplier_state=branch.state_code,
            place_of_supply=place_of_supply,
            order_discount=to_decimal(cmd.order_discount),
            apply_round_off=cmd.apply_round_off,
        )

    def preview_payment(self, cmd: CheckoutCommand) -> PaymentPreview:
        """Price a cart and validate tender composition without creating a sale."""
        result = self.quote(
            QuoteCommand(
                company_id=cmd.company_id,
                branch_id=cmd.branch_id,
                lines=cmd.lines,
                customer_id=cmd.customer_id,
                business_date=cmd.business_date,
                order_discount=cmd.order_discount,
                apply_round_off=cmd.apply_round_off,
            )
        )
        payments = self._normalize_payments(cmd)
        company = self._load_company(cmd.company_id)
        customer = self._load_customer(cmd.company_id, cmd.customer_id, for_update=False)
        payments = self._validate_customer_tenders(payments, result, customer, company)
        amount_received = money(sum((payment.amount for payment in payments), ZERO))
        change_due = money(max(ZERO, amount_received - result.net_amount))
        balance_due = money(max(ZERO, result.net_amount - amount_received))
        cash_tendered = money(
            sum(
                (payment.amount for payment in payments if payment.method == "CASH"),
                ZERO,
            )
        )
        if change_due > cash_tendered:
            raise InvalidPaymentError("Change cannot be funded by a non-cash payment.")
        return PaymentPreview(result, amount_received, change_due, balance_due)

    def _build_checkout(self, cmd: CheckoutCommand) -> Sale:
        if not 1 <= len(cmd.lines) <= 200:
            raise ValidationError("Checkout must contain between 1 and 200 lines.")
        branch, shift, company = self._require_context(cmd)
        requested = self._aggregate_quantities(cmd.lines)
        products = self._load_products(cmd.company_id, tuple(requested), for_update=True)
        self._check_stock(products, requested)
        rates = self._load_rates(cmd.company_id, products, cmd.business_date)
        customer = self._load_customer(cmd.company_id, cmd.customer_id, for_update=True)
        place_of_supply = branch.state_code
        if customer is not None:
            place_of_supply = (
                state_code_from_gstin(customer.gstin)
                if customer.gstin is not None
                else customer.state_code
            )

        tax_lines = [
            TaxLineInput(
                quantity=line.quantity,
                unit_price=products[line.product_id].selling_price,
                tax_rate=(
                    ZERO
                    if company.composition_scheme_enabled
                    else rates[products[line.product_id].tax_rate_id].rate
                ),
                cess_rate=(
                    ZERO
                    if company.composition_scheme_enabled
                    else rates[products[line.product_id].tax_rate_id].cess_rate
                ),
                line_discount=line.line_discount,
                tax_inclusive=(
                    False
                    if company.composition_scheme_enabled
                    else products[line.product_id].is_tax_inclusive
                ),
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
        payments = self._payments(cmd, result, customer, company)
        document_no, _ = InvoiceNumberService(self.session).allocate(
            cmd.company_id,
            cmd.branch_id,
            cmd.terminal_id,
            DocType.SALE.value,
            cmd.business_date,
            terminal_validated=True,
        )
        amount_paid = money(sum((payment.amount for payment in payments), ZERO))
        sale = Sale(
            company_id=cmd.company_id,
            branch_id=cmd.branch_id,
            terminal_id=cmd.terminal_id,
            customer_id=cmd.customer_id,
            cashier_id=cmd.cashier_id,
            shift_id=shift.id,
            offline_uuid=cmd.offline_uuid,
            invoice_number=document_no,
            business_date=cmd.business_date,
            sale_status="COMPLETED",
            supply_type=(
                SupplyType.INTERSTATE.value if result.is_interstate else SupplyType.INTRASTATE.value
            ),
            place_of_supply=place_of_supply,
            customer_gstin_at_sale=customer.gstin if customer is not None else None,
            customer_name_at_sale=customer.name if customer is not None else None,
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
            payment_method=payments[0].method if len(payments) == 1 else "SPLIT",
            notes=cmd.notes,
            created_by=cmd.cashier_id,
        )
        self.session.add(sale)
        self.session.flush()
        sale_items = self._add_sale_lines(cmd, sale, products, result)
        self._add_payments(cmd, sale, payments)
        InvoiceComplianceService(self.session, cmd.company_id).validate_before_issue(
            company=company,
            branch=branch,
            sale=sale,
            customer=customer,
            items=sale_items,
            products=products,
        )

        inventory = InventoryService(self.session, cmd.company_id)
        inventory_depth = InventoryDepthService(self.session, cmd.company_id)
        batch_product_ids: set[int] = set()
        for command_line, sale_item in zip(cmd.lines, sale_items, strict=True):
            product = products[command_line.product_id]
            if not product.is_inventory_tracked or not product.batch_tracking_enabled:
                continue
            batch_product_ids.add(product.id)
            inventory_depth.allocate_fefo(
                sale_item=sale_item,
                product=product,
                branch_id=cmd.branch_id,
                quantity=sale_item.quantity,
                on_date=cmd.business_date,
                expired_policy=company.expired_stock_policy,
                user_id=cmd.cashier_id,
            )
        with self.session.no_autoflush:
            for product_id in sorted(requested):
                product = products[product_id]
                if product.is_inventory_tracked and product_id not in batch_product_ids:
                    inventory.record_movement(
                        product,
                        cmd.branch_id,
                        -requested[product_id],
                        "SALE",
                        "sales",
                        sale.id,
                        cmd.cashier_id,
                        validated_branch=branch,
                        flush=False,
                    )
        if customer is not None:
            self._apply_customer_totals(cmd, sale, customer, company, result, payments)
        self.session.flush()
        return sale

    def _require_context(self, cmd: CheckoutCommand) -> tuple[Branch, Shift, Company]:
        shift_filter = (
            Shift.id == cmd.shift_id if cmd.shift_id is not None else Shift.status == "OPEN"
        )
        context = self.session.execute(
            select(Branch, Shift, Company)
            .join(
                Company,
                and_(
                    Company.id == Branch.company_id,
                    Company.deleted_at.is_(None),
                    Company.is_active.is_(True),
                ),
            )
            .join(
                Terminal,
                and_(
                    Terminal.id == cmd.terminal_id,
                    Terminal.company_id == Branch.company_id,
                    Terminal.branch_id == Branch.id,
                    Terminal.deleted_at.is_(None),
                    Terminal.is_active.is_(True),
                ),
            )
            .join(
                User,
                and_(
                    User.id == cmd.cashier_id,
                    User.company_id == Branch.company_id,
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                ),
            )
            .join(
                Shift,
                and_(
                    Shift.company_id == Branch.company_id,
                    Shift.branch_id == Branch.id,
                    Shift.terminal_id == Terminal.id,
                    Shift.cashier_id == User.id,
                    Shift.deleted_at.is_(None),
                    shift_filter,
                ),
            )
            .where(
                Branch.id == cmd.branch_id,
                Branch.company_id == cmd.company_id,
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
            )
            .with_for_update(of=Shift)
        ).one_or_none()
        if context is not None:
            branch, shift, company = context
            if shift.status == "OPEN" or cmd.offline_uuid is not None:
                return branch, shift, company

        # Invalid contexts are uncommon. Keep the specific 404 and closed-shift
        # diagnostics without paying for four round trips on every good sale.
        branch = self._require_branch(cmd.company_id, cmd.branch_id)
        company = self._load_company(cmd.company_id)
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
        shift_statement = select(Shift).where(
            Shift.company_id == cmd.company_id,
            Shift.branch_id == cmd.branch_id,
            Shift.terminal_id == cmd.terminal_id,
            Shift.cashier_id == cmd.cashier_id,
            Shift.deleted_at.is_(None),
        )
        if cmd.shift_id is not None:
            shift_statement = shift_statement.where(Shift.id == cmd.shift_id)
        else:
            shift_statement = shift_statement.where(Shift.status == "OPEN")
        shift = self.session.scalar(shift_statement.with_for_update())
        if shift is None or (shift.status != "OPEN" and cmd.offline_uuid is None):
            raise EntityNotFoundError("An open shift is required before checkout.")
        return branch, shift, company

    def _load_company(self, company_id: int) -> Company:
        company = self.session.scalar(
            select(Company).where(
                Company.id == company_id,
                Company.deleted_at.is_(None),
                Company.is_active.is_(True),
            )
        )
        if company is None:
            raise EntityNotFoundError("Company was not found.")
        return company

    def _require_branch(self, company_id: int, branch_id: int) -> Branch:
        branch = self.session.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == company_id,
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
            )
        )
        if branch is None:
            raise EntityNotFoundError("Branch was not found.")
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

    def _load_products(
        self, company_id: int, product_ids: tuple[int, ...], *, for_update: bool
    ) -> dict[int, Product]:
        statement = select(Product).where(
            Product.company_id == company_id,
            Product.id.in_(sorted(product_ids)),
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
        )
        statement = statement.order_by(Product.id)
        if for_update:
            statement = statement.with_for_update()
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

    def _load_customer(
        self, company_id: int, customer_id: int | None, *, for_update: bool
    ) -> Customer | None:
        if customer_id is None:
            return None
        statement = select(Customer).where(
            Customer.id == customer_id,
            Customer.company_id == company_id,
            Customer.deleted_at.is_(None),
            Customer.is_active.is_(True),
        )
        if for_update:
            statement = statement.with_for_update()
        customer = self.session.scalar(statement)
        if customer is None:
            raise EntityNotFoundError("Customer was not found.")
        return customer

    def _payments(
        self,
        cmd: CheckoutCommand,
        result: TaxResult,
        customer: Customer | None,
        company: Company,
    ) -> tuple[NormalizedPayment, ...]:
        normalized = self._normalize_payments(cmd)
        normalized = self._validate_customer_tenders(normalized, result, customer, company)
        tendered = money(sum((payment.amount for payment in normalized), ZERO))
        if tendered < result.net_amount:
            raise InvalidPaymentError("Tendered amount is less than the payable amount.")
        change = money(tendered - result.net_amount)
        cash_tendered = money(
            sum(
                (payment.amount for payment in normalized if payment.method == "CASH"),
                ZERO,
            )
        )
        if change > cash_tendered:
            raise InvalidPaymentError("Change cannot be funded by a non-cash payment.")
        return normalized

    def _normalize_payments(self, cmd: CheckoutCommand) -> tuple[NormalizedPayment, ...]:
        """Normalize tender rows once for previews and committed checkouts."""
        raw_payments = list(cmd.payments)
        if not raw_payments and cmd.amount_paid is not None and cmd.payment_method is not None:
            raw_payments = [PaymentCommand(cmd.payment_method, cmd.amount_paid)]
        if not raw_payments:
            raise InvalidPaymentError("At least one payment is required.")
        if len(raw_payments) > 5:
            raise InvalidPaymentError("A sale can contain at most five payment rows.")

        valid_methods = {method.value for method in PaymentMethod}
        normalized: list[NormalizedPayment] = []
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
            reference = payment.reference_number.strip() if payment.reference_number else None
            if method in {"UPI", "CARD"} and not reference:
                raise InvalidPaymentError(f"{method} payment requires a reference number.")
            normalized.append(NormalizedPayment(method, amount, reference))
        return tuple(normalized)

    def _validate_customer_tenders(
        self,
        payments: tuple[NormalizedPayment, ...],
        result: TaxResult,
        customer: Customer | None,
        company: Company,
    ) -> tuple[NormalizedPayment, ...]:
        credit_total = money(
            sum((payment.amount for payment in payments if payment.method == "CREDIT"), ZERO)
        )
        loyalty_total = money(
            sum((payment.amount for payment in payments if payment.method == "LOYALTY"), ZERO)
        )
        if (credit_total > ZERO or loyalty_total > ZERO) and customer is None:
            raise InvalidPaymentError("Credit and loyalty payments require a customer.")
        if customer is not None and credit_total > ZERO:
            available_credit = money(customer.credit_limit - customer.outstanding_balance)
            if credit_total > available_credit:
                raise InvalidPaymentError("Credit payment exceeds the customer's available limit.")
        if loyalty_total == ZERO:
            return payments
        assert customer is not None
        redemption_value = money(company.loyalty_redemption_value)
        if redemption_value <= ZERO:
            raise InvalidPaymentError("Loyalty redemption is not configured.")
        cap = money(result.net_amount * company.loyalty_redemption_cap_percent / Decimal("100"))
        if loyalty_total > cap:
            raise InvalidPaymentError("Loyalty redemption exceeds the configured bill cap.")
        loyalty_points_by_index: dict[int, Decimal] = {}
        for index, payment in enumerate(payments):
            if payment.method != "LOYALTY":
                continue
            points = qty(payment.amount / redemption_value)
            if money(points * redemption_value) != payment.amount:
                raise InvalidPaymentError("Loyalty amount does not map to supported points.")
            loyalty_points_by_index[index] = points
        required_points = qty(sum(loyalty_points_by_index.values(), Decimal("0.000")))
        if required_points > customer.loyalty_points:
            raise InvalidPaymentError("Customer does not have enough loyalty points.")
        return tuple(
            NormalizedPayment(
                payment.method,
                payment.amount,
                payment.reference_number,
                loyalty_points_by_index.get(index),
            )
            for index, payment in enumerate(payments)
        )

    def _add_sale_lines(
        self,
        cmd: CheckoutCommand,
        sale: Sale,
        products: dict[int, Product],
        result: TaxResult,
    ) -> tuple[SaleItem, ...]:
        hsn_ids = {product.hsn_id for product in products.values() if product.hsn_id is not None}
        hsn_codes = (
            {
                hsn.id: hsn.code
                for hsn in self.session.scalars(
                    select(HsnCode).where(
                        HsnCode.id.in_(sorted(hsn_ids)),
                        HsnCode.deleted_at.is_(None),
                    )
                )
            }
            if hsn_ids
            else {}
        )
        items: list[SaleItem] = []
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
                cost_at_sale=products[command_line.product_id].cost_price,
                supplier_id_at_sale=products[command_line.product_id].preferred_supplier_id,
                hsn_code_at_sale=self._hsn_snapshot(
                    hsn_codes, products[command_line.product_id].hsn_id
                ),
                uqc_at_sale=uqc_code(products[command_line.product_id].uom),
                total_amount=calculated.line_total,
                created_by=cmd.cashier_id,
            )
            self.session.add(item)
            items.append(item)
        self.session.flush()
        return tuple(items)

    @staticmethod
    def _hsn_snapshot(hsn_codes: dict[int, str], hsn_id: int | None) -> str | None:
        return hsn_codes.get(hsn_id) if hsn_id is not None else None

    def _add_payments(
        self,
        cmd: CheckoutCommand,
        sale: Sale,
        payments: tuple[NormalizedPayment, ...],
    ) -> None:
        for payment in payments:
            self.session.add(
                SalePayment(
                    company_id=cmd.company_id,
                    sale_id=sale.id,
                    payment_method=payment.method,
                    amount=payment.amount,
                    reference_number=payment.reference_number,
                    loyalty_points=payment.loyalty_points,
                    created_by=cmd.cashier_id,
                )
            )

    def _apply_customer_totals(
        self,
        cmd: CheckoutCommand,
        sale: Sale,
        customer: Customer,
        company: Company,
        result: TaxResult,
        payments: tuple[NormalizedPayment, ...],
    ) -> None:
        redeemed = qty(
            sum(
                (
                    payment.loyalty_points
                    for payment in payments
                    if payment.loyalty_points is not None
                ),
                Decimal("0.000"),
            )
        )
        credit = money(
            sum((payment.amount for payment in payments if payment.method == "CREDIT"), ZERO)
        )
        balance = qty(customer.loyalty_points - redeemed)
        if redeemed > ZERO:
            self.session.add(
                LoyaltyLedger(
                    company_id=cmd.company_id,
                    customer_id=customer.id,
                    sale_id=sale.id,
                    movement_type="REDEEM",
                    points=-redeemed,
                    balance_after=balance,
                    description=f"Redeemed on sale {sale.invoice_number}",
                    created_by=cmd.cashier_id,
                )
            )
        divisor = money(company.loyalty_earn_divisor)
        if divisor <= ZERO:
            raise InvalidPaymentError("Loyalty earning is not configured.")
        earned = qty(result.net_amount / divisor)
        balance = qty(balance + earned)
        if earned > ZERO:
            self.session.add(
                LoyaltyLedger(
                    company_id=cmd.company_id,
                    customer_id=customer.id,
                    sale_id=sale.id,
                    movement_type="EARN",
                    points=earned,
                    balance_after=balance,
                    description=f"Earned on sale {sale.invoice_number}",
                    created_by=cmd.cashier_id,
                )
            )
        self.session.execute(
            update(Customer)
            .where(
                Customer.id == customer.id,
                Customer.company_id == cmd.company_id,
                Customer.deleted_at.is_(None),
            )
            .values(
                loyalty_points=balance,
                total_spent=Customer.total_spent + result.net_amount,
                total_orders=Customer.total_orders + 1,
                outstanding_balance=Customer.outstanding_balance + credit,
                row_version=Customer.row_version + 1,
            )
        )
