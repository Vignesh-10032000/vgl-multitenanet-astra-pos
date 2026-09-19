"""Tenant-scoped customer API operations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.models import Customer, Sale
from vglpos.repositories.base import CursorPage
from vglpos.repositories.documents import SaleRepository
from vglpos.repositories.parties import CustomerRepository
from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError
from vglpos.utils.gst import STATE_CODES, state_code_from_gstin, validate_gstin


@dataclass(frozen=True, slots=True)
class CreateCustomerCommand:
    company_id: int
    user_id: int
    phone: str
    name: str
    email: str | None
    gstin: str | None
    state_code: str
    credit_limit: Decimal
    address: str | None


@dataclass(frozen=True, slots=True)
class CustomerPage:
    items: tuple[Customer, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class CustomerDetail:
    customer: Customer
    purchases: tuple[Sale, ...]


class CustomerService:
    """Create and read customer records without exposing another tenant."""

    def __init__(self, session: Session, company_id: int, *, branch_id: int | None = None) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id
        self.branch_id = branch_id
        self.repository = CustomerRepository(session, company_id)

    def list_customers(self, *, cursor: str | None, limit: int, query: str | None) -> CustomerPage:
        """Return customer search results or a stable keyset page."""
        if query is not None:
            return CustomerPage(self.repository.search(query, limit=limit), None)
        page: CursorPage[Customer] = self.repository.list(cursor=cursor, limit=limit)
        return CustomerPage(page.items, page.next_cursor)

    def create_customer(self, cmd: CreateCustomerCommand) -> Customer:
        """Normalize statutory identity and commit one customer record."""
        if cmd.company_id != self.company_id or not cmd.user_id:
            raise ValidationError("Authenticated company and user are required.")
        if cmd.state_code not in STATE_CODES:
            raise ValidationError("Customer state code is invalid.")
        gstin = cmd.gstin.strip().upper() if cmd.gstin else None
        state_code = cmd.state_code
        if gstin is not None:
            if not validate_gstin(gstin):
                raise ValidationError("Customer GSTIN is invalid.")
            gstin_state = state_code_from_gstin(gstin)
            if state_code != gstin_state:
                raise ValidationError("Customer state code does not match GSTIN.")
            state_code = gstin_state
        if self.repository.find_by_phone(cmd.phone.strip()) is not None:
            raise ConflictError("Customer phone already exists.")
        customer = Customer(
            company_id=self.company_id,
            phone=cmd.phone.strip(),
            name=cmd.name.strip(),
            email=cmd.email,
            gstin=gstin,
            state_code=state_code,
            credit_limit=cmd.credit_limit,
            address=cmd.address,
            created_by=cmd.user_id,
        )
        try:
            self.repository.add(customer)
            self.session.commit()
            self.session.refresh(customer)
            return customer
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Customer conflicts with an existing record.") from exc

    def customer_detail(self, customer_id: int) -> CustomerDetail:
        """Return one customer and recent purchases through tenant-scoped queries."""
        customer = self.repository.get(customer_id)
        if customer is None:
            raise EntityNotFoundError("Customer was not found.")
        page = SaleRepository(self.session, self.company_id).list_filtered(
            cursor=None,
            limit=50,
            branch_id=self.branch_id,
            customer_id=customer_id,
        )
        return CustomerDetail(customer=customer, purchases=page.items)
