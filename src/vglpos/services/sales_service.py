"""Sale query and cancellation operations for the API boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.events import SaleUpdated
from vglpos.domain.models import (
    Company,
    Customer,
    EInvoice,
    LoyaltyLedger,
    Product,
    Sale,
    SaleItem,
    SalePayment,
)
from vglpos.repositories.base import CursorPage
from vglpos.repositories.documents import SaleRepository
from vglpos.security.audit import record_audit_event
from vglpos.security.override_service import OverrideApprovalService
from vglpos.services.event_dispatcher import publish_event
from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError
from vglpos.services.inventory_service import InventoryService
from vglpos.services.invoice_compliance_service import InvoiceComplianceService
from vglpos.utils.money import ZERO, money, qty


@dataclass(frozen=True, slots=True)
class SaleDetail:
    sale: Sale
    items: tuple[SaleItem, ...]
    payments: tuple[SalePayment, ...]
    products: dict[int, Product]
    e_invoice: EInvoice | None
    composition_declaration: str | None


@dataclass(frozen=True, slots=True)
class CancelSaleCommand:
    company_id: int
    actor_user_id: int
    sale_id: int
    reason: str
    approver_user_id: int
    approval_pin: str


@dataclass(frozen=True, slots=True)
class ReceiptDispatch:
    sale_id: int
    invoice_number: str
    phone: str | None
    email: str | None


class SalesService:
    """Read and mutate fiscal sales only through tenant-scoped operations."""

    def __init__(self, session: Session, company_id: int, *, branch_id: int | None = None) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id
        self.branch_id = branch_id
        self.repository = SaleRepository(session, company_id)

    def list_sales(
        self,
        *,
        cursor: str | None,
        limit: int,
        branch_id: int | None,
        start_date: date | None,
        end_date: date | None,
        cashier_id: int | None,
        status: str | None,
    ) -> CursorPage[Sale]:
        """Return stable filtered sale pages without committing read-only work."""
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValidationError("Sale start date cannot be after end date.")
        return self.repository.list_filtered(
            cursor=cursor,
            limit=limit,
            branch_id=branch_id,
            start_date=start_date,
            end_date=end_date,
            cashier_id=cashier_id,
            status=status,
        )

    def sale_detail(self, sale_id: int) -> SaleDetail:
        """Return an invoice aggregate or the same 404 for foreign tenant IDs."""
        sale = self._get_sale(sale_id)
        items = self.repository.items(sale.id)
        product_ids = tuple(item.product_id for item in items)
        products = {
            product.id: product
            for product in self.session.scalars(
                select(Product).where(
                    Product.company_id == self.company_id,
                    Product.id.in_(product_ids),
                )
            )
        }
        if len(products) != len(set(product_ids)):
            raise EntityNotFoundError("Sale product was not found.")
        e_invoice = self.session.scalar(
            select(EInvoice).where(
                EInvoice.company_id == self.company_id,
                EInvoice.sale_id == sale.id,
                EInvoice.deleted_at.is_(None),
            )
        )
        company = self.session.scalar(
            select(Company).where(
                Company.id == self.company_id,
                Company.deleted_at.is_(None),
            )
        )
        return SaleDetail(
            sale=sale,
            items=items,
            payments=self.repository.payments(sale.id),
            products=products,
            e_invoice=e_invoice,
            composition_declaration=(
                company.composition_declaration
                if company is not None and company.composition_scheme_enabled
                else None
            ),
        )

    def cancel_sale(self, cmd: CancelSaleCommand) -> Sale:
        """Void one completed sale and restore stock and customer counters atomically."""
        if cmd.company_id != self.company_id or not cmd.reason.strip():
            raise ValidationError("Authenticated company and cancellation reason are required.")
        sale = self._get_sale(cmd.sale_id, for_update=True)
        if sale.sale_status != "COMPLETED":
            raise ConflictError("Only a completed, unreturned sale can be voided.")
        InvoiceComplianceService(self.session, self.company_id).enforce_sale_cancellation(sale)
        OverrideApprovalService(self.session).approve_void(
            company_id=self.company_id,
            actor_user_id=cmd.actor_user_id,
            sale_id=sale.id,
            approval_pin=cmd.approval_pin,
            approver_user_id=cmd.approver_user_id,
            reason=cmd.reason,
        )
        items = self.repository.items(sale.id)
        inventory = InventoryService(self.session, self.company_id)
        for item in items:
            product = self.session.scalar(
                select(Product).where(
                    Product.id == item.product_id,
                    Product.company_id == self.company_id,
                )
            )
            if product is None:
                raise EntityNotFoundError("Sale product was not found.")
            if product.is_inventory_tracked:
                inventory.record_movement(
                    product,
                    sale.branch_id,
                    item.quantity,
                    "SALE_VOID",
                    "sales",
                    sale.id,
                    cmd.actor_user_id,
                    allow_deleted=True,
                )
        self._reverse_customer_counters(sale, actor_user_id=cmd.actor_user_id)
        sale.sale_status = "CANCELLED"
        sale.cancelled_at = datetime.now(UTC)
        sale.cancellation_reason = cmd.reason.strip()
        sale.updated_by = cmd.actor_user_id
        sale.row_version += 1
        try:
            self.session.commit()
            self.session.refresh(sale)
            publish_event(
                SaleUpdated(
                    company_id=self.company_id,
                    branch_id=sale.branch_id,
                    sale_id=sale.id,
                    occurred_at=datetime.now(UTC),
                )
            )
            return sale
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Sale cancellation conflicted with current state.") from exc

    def receipt_dispatch(self, sale_id: int, *, channel: str = "WHATSAPP") -> ReceiptDispatch:
        """Resolve a stored customer destination without accepting arbitrary recipients."""
        sale = self._get_sale(sale_id)
        if sale.customer_id is None:
            raise ValidationError("Sale has no customer for receipt delivery.")
        customer = self.session.scalar(
            select(Customer).where(
                Customer.id == sale.customer_id,
                Customer.company_id == self.company_id,
                Customer.deleted_at.is_(None),
            )
        )
        if customer is None:
            raise ValidationError("Sale customer was not found for receipt delivery.")
        normalized_channel = channel.strip().upper()
        if normalized_channel in {"WHATSAPP", "SMS"} and not customer.phone.strip():
            raise ValidationError("Sale customer has no delivery phone.")
        if normalized_channel == "EMAIL" and not (customer.email and customer.email.strip()):
            raise ValidationError("Sale customer has no delivery email.")
        if normalized_channel not in {"WHATSAPP", "SMS", "EMAIL"}:
            raise ValidationError("Unsupported receipt delivery channel.")
        return ReceiptDispatch(sale.id, sale.invoice_number, customer.phone, customer.email)

    def record_reprint(self, sale_id: int, *, user_id: int) -> Sale:
        """Audit every receipt reprint before allowing the browser to print it."""
        if not user_id:
            raise ValidationError("Authenticated user is required for a reprint.")
        sale = self._get_sale(sale_id)
        record_audit_event(
            self.session,
            company_id=self.company_id,
            user_id=user_id,
            action="RECEIPT_REPRINT",
            entity_type="Sale",
            entity_id=sale.id,
            new_values={"invoice_number": sale.invoice_number},
        )
        self.session.commit()
        return sale

    def _get_sale(self, sale_id: int, *, for_update: bool = False) -> Sale:
        sale = self.repository.get(sale_id, for_update=for_update)
        if sale is None or (self.branch_id is not None and sale.branch_id != self.branch_id):
            raise EntityNotFoundError("Sale was not found.")
        return sale

    def _reverse_customer_counters(self, sale: Sale, *, actor_user_id: int) -> None:
        if sale.customer_id is None:
            return
        customer = self.session.scalar(
            select(Customer)
            .where(
                Customer.id == sale.customer_id,
                Customer.company_id == self.company_id,
                Customer.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if customer is None:
            raise EntityNotFoundError("Sale customer was not found.")
        loyalty_rows = self.session.execute(
            select(LoyaltyLedger.movement_type, func.sum(LoyaltyLedger.points))
            .where(
                LoyaltyLedger.company_id == self.company_id,
                LoyaltyLedger.sale_id == sale.id,
                LoyaltyLedger.credit_note_id.is_(None),
                LoyaltyLedger.deleted_at.is_(None),
            )
            .group_by(LoyaltyLedger.movement_type)
        ).all()
        movements = {movement_type: qty(points) for movement_type, points in loyalty_rows}
        earned = max(Decimal("0.000"), movements.get("EARN", Decimal("0.000")))
        redeemed = abs(min(Decimal("0.000"), movements.get("REDEEM", Decimal("0.000"))))
        balance = qty(customer.loyalty_points)
        if earned > ZERO:
            balance = qty(balance - earned)
            self.session.add(
                LoyaltyLedger(
                    company_id=self.company_id,
                    customer_id=customer.id,
                    sale_id=sale.id,
                    movement_type="EARN_REVERSAL",
                    points=-earned,
                    balance_after=balance,
                    description=f"Earn reversal on void {sale.invoice_number}",
                    created_by=actor_user_id,
                )
            )
        if redeemed > ZERO:
            balance = qty(balance + redeemed)
            self.session.add(
                LoyaltyLedger(
                    company_id=self.company_id,
                    customer_id=customer.id,
                    sale_id=sale.id,
                    movement_type="REDEEM_REVERSAL",
                    points=redeemed,
                    balance_after=balance,
                    description=f"Redemption reversal on void {sale.invoice_number}",
                    created_by=actor_user_id,
                )
            )
        credit_total = money(
            self.session.scalar(
                select(func.coalesce(func.sum(SalePayment.amount), ZERO)).where(
                    SalePayment.company_id == self.company_id,
                    SalePayment.sale_id == sale.id,
                    SalePayment.payment_method == "CREDIT",
                    SalePayment.deleted_at.is_(None),
                )
            )
            or ZERO
        )
        customer.loyalty_points = balance
        customer.outstanding_balance = max(ZERO, money(customer.outstanding_balance - credit_total))
        customer.total_spent = max(ZERO, money(customer.total_spent - sale.net_amount))
        if customer.total_orders > 0:
            customer.total_orders -= 1
        customer.row_version += 1
