"""Sale query and cancellation operations for the API boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.events import SaleUpdated
from vglpos.domain.models import Customer, Product, Sale, SaleItem, SalePayment
from vglpos.repositories.base import CursorPage
from vglpos.repositories.documents import SaleRepository
from vglpos.security.override_service import OverrideApprovalService
from vglpos.services.checkout_service import LOYALTY_EARN_DIVISOR
from vglpos.services.event_dispatcher import publish_event
from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError
from vglpos.services.inventory_service import InventoryService
from vglpos.utils.money import ZERO, money, qty


@dataclass(frozen=True, slots=True)
class SaleDetail:
    sale: Sale
    items: tuple[SaleItem, ...]
    payments: tuple[SalePayment, ...]


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
    phone: str


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
        return SaleDetail(
            sale=sale,
            items=self.repository.items(sale.id),
            payments=self.repository.payments(sale.id),
        )

    def cancel_sale(self, cmd: CancelSaleCommand) -> Sale:
        """Void one completed sale and restore stock and customer counters atomically."""
        if cmd.company_id != self.company_id or not cmd.reason.strip():
            raise ValidationError("Authenticated company and cancellation reason are required.")
        sale = self._get_sale(cmd.sale_id, for_update=True)
        if sale.sale_status != "COMPLETED":
            raise ConflictError("Only a completed, unreturned sale can be voided.")
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
        self._reverse_customer_counters(sale)
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

    def receipt_dispatch(self, sale_id: int) -> ReceiptDispatch:
        """Resolve a stored customer phone without accepting an arbitrary destination."""
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
        if customer is None or not customer.phone.strip():
            raise ValidationError("Sale customer has no delivery phone.")
        return ReceiptDispatch(sale.id, sale.invoice_number, customer.phone)

    def _get_sale(self, sale_id: int, *, for_update: bool = False) -> Sale:
        sale = self.repository.get(sale_id, for_update=for_update)
        if sale is None or (self.branch_id is not None and sale.branch_id != self.branch_id):
            raise EntityNotFoundError("Sale was not found.")
        return sale

    def _reverse_customer_counters(self, sale: Sale) -> None:
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
        reversed_points = qty(sale.net_amount / LOYALTY_EARN_DIVISOR)
        customer.loyalty_points = max(Decimal("0.000"), customer.loyalty_points - reversed_points)
        customer.total_spent = max(ZERO, money(customer.total_spent - sale.net_amount))
        if customer.total_orders > 0:
            customer.total_orders -= 1
        customer.row_version += 1
