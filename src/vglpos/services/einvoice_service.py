"""Durable e-invoice and e-way bill mapping, queueing, and reconciliation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.models import (
    Branch,
    Company,
    Customer,
    EInvoice,
    EWayBill,
    Product,
    Sale,
    SaleItem,
)
from vglpos.services.einvoice_schema import (
    BuyerDetails,
    DocumentDetails,
    EInvoicePayload,
    EWayBillPayload,
    EWayItem,
    ItemDetails,
    SellerDetails,
    TransactionDetails,
    ValueDetails,
)
from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError
from vglpos.services.irp_client import (
    IRPClient,
    IRPPermanentError,
    IRPTransientError,
)
from vglpos.services.report_export_service import JsonValue, decimal_json_dumps
from vglpos.utils.gst import state_code_from_gstin, validate_gstin
from vglpos.utils.money import ZERO, money

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EWayBillCommand:
    company_id: int
    sale_id: int
    user_id: int
    distance_km: int
    transporter_id: str | None = None
    transporter_name: str | None = None
    transport_mode: str = "1"
    transport_document_number: str | None = None
    transport_document_date: date | None = None
    vehicle_number: str | None = None
    vehicle_type: str | None = None


@dataclass(frozen=True, slots=True)
class ComplianceAlert:
    pending_count: int
    dead_letter_count: int
    oldest_pending_at: datetime | None
    exceeds_queue_limit: bool
    exceeds_reporting_window: bool

    @property
    def active(self) -> bool:
        """Signal only actionable queue volume, age, or dead-letter conditions."""
        return (
            self.exceeds_queue_limit or self.exceeds_reporting_window or self.dead_letter_count > 0
        )


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    sale_id: int
    invoice_number: str
    business_date: date
    issue: str
    status: str | None
    error_text: str | None


@dataclass(frozen=True, slots=True)
class _InvoiceContext:
    company: Company
    branch: Branch
    sale: Sale
    customer: Customer
    items: tuple[SaleItem, ...]
    products: dict[int, Product]


class EInvoiceMapper:
    """Map immutable sale tax facts into locally validated government schemas."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def invoice_json(self, sale_id: int) -> str:
        """Return schema-1.1 JSON without converting Decimal money through binary float."""
        context = self._context(sale_id, require_registered_buyer=True)
        items = self._invoice_items(context)
        payload = EInvoicePayload(
            transaction=TransactionDetails(),
            document=DocumentDetails(
                number=context.sale.invoice_number,
                document_date=context.sale.business_date.strftime("%d/%m/%Y"),
            ),
            seller=self._seller(context),
            buyer=self._buyer(context),
            items=items,
            values=ValueDetails(
                assessable_value=context.sale.taxable_amount,
                cgst_value=context.sale.cgst_amount,
                sgst_value=context.sale.sgst_amount,
                igst_value=context.sale.igst_amount,
                cess_value=context.sale.cess_amount,
                discount=money(sum((item.discount for item in items), ZERO)),
                other_charges=context.sale.round_off,
                total_invoice_value=context.sale.net_amount,
            ),
        )
        return self._json(payload)

    def eway_json(self, command: EWayBillCommand) -> str:
        """Return the official e-way bill shape from the same stored sale components."""
        context = self._context(command.sale_id, require_registered_buyer=False)
        if not 1 <= command.distance_km <= 4000:
            raise ValidationError("Transport distance must be between 1 and 4000 km.")
        if command.transport_mode not in {"1", "2", "3", "4"}:
            raise ValidationError("Transport mode must be 1, 2, 3, or 4.")
        if command.transport_mode == "1" and not command.vehicle_number:
            raise ValidationError("Road transport requires a vehicle number.")
        buyer = self._buyer(context)
        seller = self._seller(context)
        payload = EWayBillPayload(
            document_number=context.sale.invoice_number,
            document_date=context.sale.business_date.strftime("%d/%m/%Y"),
            from_gstin=seller.gstin,
            from_trade_name=seller.trade_name or seller.legal_name,
            from_address1=seller.address_line1,
            from_address2=seller.address_line2,
            from_place=seller.location,
            from_pincode=seller.postal_code,
            actual_from_state_code=int(seller.state_code),
            from_state_code=int(seller.state_code),
            to_gstin=buyer.gstin if context.customer.gstin else "URP",
            to_trade_name=buyer.trade_name or buyer.legal_name,
            to_address1=buyer.address_line1,
            to_place=buyer.location,
            to_pincode=buyer.postal_code,
            actual_to_state_code=int(buyer.state_code),
            to_state_code=int(buyer.state_code),
            total_value=context.sale.taxable_amount,
            cgst_value=context.sale.cgst_amount,
            sgst_value=context.sale.sgst_amount,
            igst_value=context.sale.igst_amount,
            cess_value=context.sale.cess_amount,
            other_value=context.sale.round_off,
            total_invoice_value=context.sale.net_amount,
            transporter_id=command.transporter_id,
            transporter_name=command.transporter_name,
            transport_mode=command.transport_mode,
            transport_distance=str(command.distance_km),
            transport_document_number=command.transport_document_number,
            transport_document_date=(
                command.transport_document_date.strftime("%d/%m/%Y")
                if command.transport_document_date
                else None
            ),
            vehicle_number=command.vehicle_number,
            vehicle_type=command.vehicle_type,
            items=self._eway_items(context),
        )
        return self._json(payload)

    def _context(self, sale_id: int, *, require_registered_buyer: bool) -> _InvoiceContext:
        sale = self.session.scalar(
            select(Sale).where(
                Sale.id == sale_id,
                Sale.company_id == self.company_id,
                Sale.deleted_at.is_(None),
            )
        )
        if sale is None:
            raise EntityNotFoundError("Sale was not found.")
        if sale.sale_status != "COMPLETED":
            raise ConflictError("Only a completed sale can be submitted for compliance.")
        company = self.session.scalar(
            select(Company).where(Company.id == self.company_id, Company.deleted_at.is_(None))
        )
        branch = self.session.scalar(
            select(Branch).where(
                Branch.id == sale.branch_id,
                Branch.company_id == self.company_id,
                Branch.deleted_at.is_(None),
            )
        )
        customer = self.session.scalar(
            select(Customer).where(
                Customer.id == sale.customer_id,
                Customer.company_id == self.company_id,
                Customer.deleted_at.is_(None),
            )
        )
        if company is None or branch is None:
            raise EntityNotFoundError("Invoice supplier was not found.")
        if customer is None:
            raise ValidationError("E-invoice and e-way bill generation require a named customer.")
        if require_registered_buyer and not customer.gstin:
            raise ValidationError("E-invoice generation requires a registered buyer GSTIN.")
        items = tuple(
            self.session.scalars(
                select(SaleItem)
                .where(
                    SaleItem.company_id == self.company_id,
                    SaleItem.sale_id == sale.id,
                    SaleItem.deleted_at.is_(None),
                )
                .order_by(SaleItem.line_number)
            )
        )
        products = {
            product.id: product
            for product in self.session.scalars(
                select(Product).where(
                    Product.company_id == self.company_id,
                    Product.id.in_({item.product_id for item in items}),
                    Product.deleted_at.is_(None),
                )
            )
        }
        if not items or len(products) != len({item.product_id for item in items}):
            raise EntityNotFoundError("Invoice item catalogue facts were not found.")
        return _InvoiceContext(company, branch, sale, customer, items, products)

    @staticmethod
    def _seller(context: _InvoiceContext) -> SellerDetails:
        gstin = context.branch.gstin or context.company.gstin
        if not gstin:
            raise ValidationError("Supplier GSTIN is required for IRP submission.")
        if not validate_gstin(gstin):
            raise ValidationError("Supplier GSTIN is invalid.")
        if state_code_from_gstin(gstin) != context.branch.state_code:
            raise ValidationError("Supplier GSTIN does not match the branch state.")
        return SellerDetails(
            gstin=gstin,
            legal_name=context.company.legal_name,
            trade_name=context.company.name,
            address_line1=context.branch.address_line1,
            address_line2=context.branch.address_line2,
            location=context.branch.city,
            postal_code=EInvoiceMapper._pincode(context.branch.postal_code, "Supplier"),
            state_code=context.branch.state_code,
            phone=context.branch.phone,
            email=context.company.contact_email,
        )

    @staticmethod
    def _buyer(context: _InvoiceContext) -> BuyerDetails:
        customer = context.customer
        if not customer.address or not customer.city or not customer.postal_code:
            raise ValidationError("Buyer address, city, and postal code are required.")
        if customer.gstin and not validate_gstin(customer.gstin):
            raise ValidationError("Buyer GSTIN is invalid.")
        if customer.gstin and state_code_from_gstin(customer.gstin) != customer.state_code:
            raise ValidationError("Buyer GSTIN does not match the customer state.")
        return BuyerDetails(
            gstin=customer.gstin or "URP",
            legal_name=context.sale.customer_name_at_sale or customer.name,
            trade_name=context.sale.customer_name_at_sale or customer.name,
            place_of_supply=context.sale.place_of_supply or customer.state_code,
            address_line1=customer.address,
            location=customer.city,
            postal_code=EInvoiceMapper._pincode(customer.postal_code, "Buyer"),
            state_code=customer.state_code,
            phone=customer.phone,
            email=customer.email,
        )

    @staticmethod
    def _invoice_items(context: _InvoiceContext) -> list[ItemDetails]:
        result: list[ItemDetails] = []
        for item in context.items:
            hsn = item.hsn_code_at_sale
            if not hsn:
                raise ValidationError(f"Sale line {item.line_number} is missing its HSN snapshot.")
            product = context.products[item.product_id]
            total_amount = item.gross_amount
            discount = item.discount_amount
            if money(item.gross_amount - item.discount_amount) != item.taxable_amount:
                combined_rate = item.tax_rate + item.cess_rate
                divisor = Decimal("1") + combined_rate / Decimal("100")
                total_amount = money(item.gross_amount / divisor)
                discount = money(total_amount - item.taxable_amount)
                if discount < ZERO:
                    raise ValidationError(
                        f"Sale line {item.line_number} has inconsistent tax-inclusive values."
                    )
            result.append(
                ItemDetails(
                    serial_number=str(item.line_number),
                    description=product.name,
                    hsn_code=hsn,
                    quantity=item.quantity,
                    unit=item.uqc_at_sale,
                    unit_price=money(total_amount / item.quantity),
                    total_amount=total_amount,
                    discount=discount,
                    assessable_amount=item.taxable_amount,
                    gst_rate=item.tax_rate,
                    igst_amount=item.igst_amount,
                    cgst_amount=item.cgst_amount,
                    sgst_amount=item.sgst_amount,
                    cess_rate=item.cess_rate,
                    cess_amount=item.cess_amount,
                    total_item_value=item.total_amount,
                )
            )
        return result

    @staticmethod
    def _eway_items(context: _InvoiceContext) -> list[EWayItem]:
        result: list[EWayItem] = []
        for item in context.items:
            hsn = item.hsn_code_at_sale
            if not hsn:
                raise ValidationError(f"Sale line {item.line_number} is missing its HSN snapshot.")
            product = context.products[item.product_id]
            result.append(
                EWayItem(
                    product_name=product.name,
                    product_description=product.name,
                    hsn_code=int(hsn),
                    quantity=item.quantity,
                    quantity_unit=item.uqc_at_sale,
                    cgst_rate=item.cgst_rate,
                    sgst_rate=item.sgst_rate,
                    igst_rate=item.igst_rate,
                    cess_rate=item.cess_rate,
                    taxable_amount=item.taxable_amount,
                )
            )
        return result

    @staticmethod
    def _pincode(value: str, label: str) -> int:
        if len(value) != 6 or not value.isdigit():
            raise ValidationError(f"{label} postal code must contain exactly six digits.")
        return int(value)

    @staticmethod
    def _json(payload: EInvoicePayload | EWayBillPayload) -> str:
        try:
            tree = cast(JsonValue, payload.model_dump(by_alias=True, exclude_none=True))
            return decimal_json_dumps(tree)
        except (PydanticValidationError, ValueError) as exc:
            raise ValidationError(
                f"Compliance payload does not match the local schema: {exc}"
            ) from exc


class EInvoiceService:
    """Own durable IRP state so retries never mutate or block the sale aggregate."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def queue_sale(self, sale_id: int) -> EInvoice | None:
        """Create one idempotent pending record after checkout has already committed."""
        company = self._company()
        sale = self._sale(sale_id)
        if (
            not company.e_invoice_enabled
            or company.composition_scheme_enabled
            or not sale.customer_gstin_at_sale
        ):
            return None
        existing = self.session.scalar(
            select(EInvoice).where(
                EInvoice.company_id == self.company_id,
                EInvoice.sale_id == sale.id,
                EInvoice.deleted_at.is_(None),
            )
        )
        if existing is not None:
            return existing
        record = EInvoice(
            company_id=self.company_id,
            sale_id=sale.id,
            provider=company.e_invoice_provider,
            status="PENDING",
            max_attempts=company.e_invoice_retry_limit,
            created_by=sale.cashier_id,
        )
        try:
            record.request_json = EInvoiceMapper(self.session, self.company_id).invoice_json(
                sale.id
            )
        except (ValidationError, PydanticValidationError, ValueError) as exc:
            record.status = "DEAD"
            record.error_code = "LOCAL_SCHEMA"
            record.error_text = str(exc)
        self.session.add(record)
        try:
            self.session.commit()
            self.session.refresh(record)
            return record
        except IntegrityError:
            self.session.rollback()
            return self.session.scalar(
                select(EInvoice).where(
                    EInvoice.company_id == self.company_id,
                    EInvoice.sale_id == sale.id,
                    EInvoice.deleted_at.is_(None),
                )
            )

    def process(self, record_id: int, client: IRPClient) -> EInvoice:
        """Submit or cancel one record while persisting every retry/dead-letter transition."""
        record = self._record(record_id, for_update=True)
        if record.status in {"GENERATED", "CANCELLED", "DEAD"}:
            return record
        cancelling = record.status in {"CANCEL_PENDING", "CANCEL_RETRY"}
        if record.request_json is None or record.attempt_count >= record.max_attempts:
            return self._dead(record, "RETRY_LIMIT", "Compliance retry limit was reached.")
        record.status = "PROCESSING"
        record.attempt_count += 1
        record.last_attempt_at = datetime.now(UTC)
        record.next_attempt_at = None
        self.session.commit()
        try:
            if cancelling:
                self._cancel(record, client)
            else:
                result = client.generate_invoice(record.request_json)
                record.irn = result.irn
                record.ack_number = result.ack_number
                record.ack_date = result.ack_date
                record.signed_invoice = result.signed_invoice
                record.signed_qr_code = result.signed_qr_code
                record.response_json = result.raw_json
                record.status = "GENERATED"
                record.generated_at = datetime.now(UTC)
                record.error_code = None
                record.error_text = None
                record.next_attempt_at = None
                self.session.commit()
        except IRPTransientError as exc:
            self._failure(record, exc, cancelling=cancelling, transient=True)
        except IRPPermanentError as exc:
            self._failure(record, exc, cancelling=cancelling, transient=False)
        self.session.refresh(record)
        return record

    def request_cancellation(self, record_id: int, *, user_id: int, reason: str) -> EInvoice:
        """Queue IRN cancellation only inside the 24-hour provider window."""
        if not user_id or not reason.strip():
            raise ValidationError("Authenticated user and cancellation reason are required.")
        record = self._record(record_id, for_update=True)
        if record.status != "GENERATED" or not record.irn or not record.ack_date:
            raise ConflictError("Only a generated e-invoice can be cancelled.")
        if datetime.now(UTC) - self._aware(record.ack_date) > timedelta(hours=24):
            raise ConflictError("The 24-hour IRN cancellation window has expired.")
        record.status = "CANCEL_PENDING"
        record.cancel_reason = reason.strip()
        record.attempt_count = 0
        record.error_code = None
        record.error_text = None
        record.updated_by = user_id
        record.row_version += 1
        self.session.commit()
        self.session.refresh(record)
        return record

    def retry(self, record_id: int, *, user_id: int) -> EInvoice:
        """Move a failed record back to pending after explicit administrator review."""
        record = self._record(record_id, for_update=True)
        if record.status not in {"DEAD", "RETRY", "CANCEL_RETRY"}:
            raise ConflictError("Only retryable or dead-letter e-invoices can be retried.")
        cancelling = bool(record.irn and record.cancel_reason)
        if not cancelling:
            try:
                record.request_json = EInvoiceMapper(self.session, self.company_id).invoice_json(
                    record.sale_id
                )
            except (ValidationError, PydanticValidationError, ValueError) as exc:
                raise ValidationError(
                    f"E-invoice data is still invalid and cannot be retried: {exc}"
                ) from exc
        record.status = "CANCEL_PENDING" if cancelling else "PENDING"
        record.attempt_count = 0
        record.next_attempt_at = None
        record.error_code = None
        record.error_text = None
        record.updated_by = user_id
        record.row_version += 1
        self.session.commit()
        self.session.refresh(record)
        return record

    def list(self, *, status: str | None = None, limit: int = 100) -> tuple[EInvoice, ...]:
        """Return the newest tenant records for the compliance administration screen."""
        statement = select(EInvoice).where(
            EInvoice.company_id == self.company_id, EInvoice.deleted_at.is_(None)
        )
        if status:
            statement = statement.where(EInvoice.status == status.strip().upper())
        return tuple(
            self.session.scalars(
                statement.order_by(EInvoice.created_at.desc(), EInvoice.id).limit(limit)
            )
        )

    def alert(self, *, now: datetime | None = None) -> ComplianceAlert:
        """Detect queue pressure and records nearing the configured reporting deadline."""
        current = now or datetime.now(UTC)
        company = self._company()
        pending_statuses = ("PENDING", "PROCESSING", "RETRY", "CANCEL_PENDING", "CANCEL_RETRY")
        pending_count, oldest = self.session.execute(
            select(func.count(EInvoice.id), func.min(EInvoice.created_at)).where(
                EInvoice.company_id == self.company_id,
                EInvoice.status.in_(pending_statuses),
                EInvoice.deleted_at.is_(None),
            )
        ).one()
        dead_count = int(
            self.session.scalar(
                select(func.count(EInvoice.id)).where(
                    EInvoice.company_id == self.company_id,
                    EInvoice.status == "DEAD",
                    EInvoice.deleted_at.is_(None),
                )
            )
            or 0
        )
        oldest_at = oldest if isinstance(oldest, datetime) else None
        overdue = bool(
            oldest_at
            and current - self._aware(oldest_at)
            >= timedelta(days=company.e_invoice_reporting_window_days)
        )
        count = int(pending_count or 0)
        return ComplianceAlert(count, dead_count, oldest_at, count > 50, overdue)

    def reconciliation(self) -> tuple[ReconciliationIssue, ...]:
        """Report every qualifying completed B2B sale without a generated IRN."""
        company = self._company()
        if not company.e_invoice_enabled or company.composition_scheme_enabled:
            return ()
        rows = self.session.execute(
            select(Sale, EInvoice)
            .outerjoin(
                EInvoice,
                (EInvoice.company_id == Sale.company_id)
                & (EInvoice.sale_id == Sale.id)
                & EInvoice.deleted_at.is_(None),
            )
            .where(
                Sale.company_id == self.company_id,
                Sale.sale_status == "COMPLETED",
                Sale.customer_gstin_at_sale.is_not(None),
                Sale.deleted_at.is_(None),
            )
            .order_by(Sale.business_date, Sale.id)
        )
        issues: list[ReconciliationIssue] = []
        for sale, record in rows:
            if record is None:
                issues.append(
                    ReconciliationIssue(
                        sale.id, sale.invoice_number, sale.business_date, "MISSING", None, None
                    )
                )
            elif record.status != "GENERATED":
                issues.append(
                    ReconciliationIssue(
                        sale.id,
                        sale.invoice_number,
                        sale.business_date,
                        "IRN_NOT_GENERATED",
                        record.status,
                        record.error_text,
                    )
                )
        return tuple(issues)

    def recover_stale_processing(
        self, *, now: datetime | None = None, stale_after: timedelta = timedelta(minutes=5)
    ) -> tuple[EInvoice, ...]:
        """Return worker-interrupted records to a retry state for reconciliation dispatch."""
        current = now or datetime.now(UTC)
        records = tuple(
            self.session.scalars(
                select(EInvoice)
                .where(
                    EInvoice.company_id == self.company_id,
                    EInvoice.status == "PROCESSING",
                    EInvoice.last_attempt_at <= current - stale_after,
                    EInvoice.deleted_at.is_(None),
                )
                .with_for_update()
            )
        )
        for record in records:
            record.status = (
                "CANCEL_RETRY" if record.irn is not None and record.cancel_reason else "RETRY"
            )
            record.next_attempt_at = current
            record.error_code = "WORKER_INTERRUPTED"
            record.error_text = "The previous compliance worker stopped before completion."
        if records:
            self.session.commit()
        return records

    def _cancel(self, record: EInvoice, client: IRPClient) -> None:
        if not record.irn or not record.cancel_reason or not record.ack_date:
            raise IRPPermanentError("Stored e-invoice cancellation data is incomplete.")
        if datetime.now(UTC) - self._aware(record.ack_date) > timedelta(hours=24):
            raise IRPPermanentError("The 24-hour IRN cancellation window has expired.")
        gstin = self._request_gstin(record.request_json or "")
        result = client.cancel_invoice(gstin=gstin, irn=record.irn, reason=record.cancel_reason)
        record.status = "CANCELLED"
        record.cancelled_at = result.cancelled_at
        record.response_json = result.raw_json
        record.error_code = None
        record.error_text = None
        record.next_attempt_at = None
        self.session.commit()

    def _failure(
        self,
        record: EInvoice,
        exc: IRPTransientError | IRPPermanentError,
        *,
        cancelling: bool,
        transient: bool,
    ) -> None:
        exhausted = record.attempt_count >= record.max_attempts
        if transient and not exhausted:
            record.status = "CANCEL_RETRY" if cancelling else "RETRY"
            delay_seconds = min(3600, 30 * (2 ** min(record.attempt_count - 1, 7)))
            record.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        else:
            record.status = "DEAD"
            record.next_attempt_at = None
        record.error_code = exc.code or type(exc).__name__
        record.error_text = str(exc)
        self.session.commit()
        logger.warning(
            "e_invoice_processing_failed",
            extra={
                "company_id": self.company_id,
                "record_id": record.id,
                "status": record.status,
                "error_code": record.error_code,
            },
        )

    def _dead(self, record: EInvoice, code: str, message: str) -> EInvoice:
        record.status = "DEAD"
        record.error_code = code
        record.error_text = message
        record.next_attempt_at = None
        self.session.commit()
        self.session.refresh(record)
        return record

    def _company(self) -> Company:
        company = self.session.scalar(
            select(Company).where(Company.id == self.company_id, Company.deleted_at.is_(None))
        )
        if company is None:
            raise EntityNotFoundError("Company was not found.")
        return company

    def _sale(self, sale_id: int) -> Sale:
        sale = self.session.scalar(
            select(Sale).where(
                Sale.id == sale_id,
                Sale.company_id == self.company_id,
                Sale.deleted_at.is_(None),
            )
        )
        if sale is None:
            raise EntityNotFoundError("Sale was not found.")
        return sale

    def _record(self, record_id: int, *, for_update: bool) -> EInvoice:
        statement = select(EInvoice).where(
            EInvoice.id == record_id,
            EInvoice.company_id == self.company_id,
            EInvoice.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        record = self.session.scalar(statement)
        if record is None:
            raise EntityNotFoundError("E-invoice was not found.")
        return record

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _request_gstin(payload_json: str) -> str:
        try:
            payload = json.loads(payload_json, parse_float=Decimal)
            value = payload["SellerDtls"]["Gstin"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise IRPPermanentError("Stored e-invoice payload has no supplier GSTIN.") from exc
        if not isinstance(value, str):
            raise IRPPermanentError("Stored e-invoice supplier GSTIN is invalid.")
        return value


class EWayBillService:
    """Queue and process e-way bills with the same durable retry/dead-letter pattern."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def create(self, command: EWayBillCommand) -> EWayBill:
        """Validate transport facts locally and create one idempotent pending record."""
        if command.company_id != self.company_id or not command.user_id:
            raise ValidationError("Authenticated company and user are required.")
        company = self._company()
        existing = self.session.scalar(
            select(EWayBill).where(
                EWayBill.company_id == self.company_id,
                EWayBill.sale_id == command.sale_id,
                EWayBill.deleted_at.is_(None),
            )
        )
        if existing is not None:
            return existing
        try:
            payload = EInvoiceMapper(self.session, self.company_id).eway_json(command)
        except PydanticValidationError as exc:
            raise ValidationError(
                f"E-way bill payload does not match the local schema: {exc}"
            ) from exc
        record = EWayBill(
            company_id=self.company_id,
            sale_id=command.sale_id,
            provider=company.e_invoice_provider,
            status="PENDING",
            request_json=payload,
            distance_km=command.distance_km,
            transporter_id=command.transporter_id,
            transporter_name=command.transporter_name,
            transport_mode=command.transport_mode,
            transport_document_number=command.transport_document_number,
            transport_document_date=command.transport_document_date,
            vehicle_number=command.vehicle_number,
            vehicle_type=command.vehicle_type,
            max_attempts=company.e_invoice_retry_limit,
            created_by=command.user_id,
        )
        self.session.add(record)
        try:
            self.session.commit()
            self.session.refresh(record)
            return record
        except IntegrityError as exc:
            self.session.rollback()
            existing = self.session.scalar(
                select(EWayBill).where(
                    EWayBill.company_id == self.company_id,
                    EWayBill.sale_id == command.sale_id,
                    EWayBill.deleted_at.is_(None),
                )
            )
            if existing is not None:
                return existing
            raise ConflictError("E-way bill request conflicts with existing state.") from exc

    def process(self, record_id: int, client: IRPClient) -> EWayBill:
        """Submit one e-way bill and retain retryable provider failures."""
        record = self._record(record_id, for_update=True)
        if record.status in {"GENERATED", "DEAD"}:
            return record
        if record.attempt_count >= record.max_attempts:
            record.status = "DEAD"
            record.error_code = "RETRY_LIMIT"
            record.error_text = "Compliance retry limit was reached."
            self.session.commit()
            return record
        record.status = "PROCESSING"
        record.attempt_count += 1
        record.last_attempt_at = datetime.now(UTC)
        record.next_attempt_at = None
        self.session.commit()
        try:
            result = client.generate_eway_bill(record.request_json)
            record.eway_bill_number = result.number
            record.eway_bill_date = result.generated_at
            record.valid_until = result.valid_until
            record.response_json = result.raw_json
            record.status = "GENERATED"
            record.generated_at = datetime.now(UTC)
            record.error_code = None
            record.error_text = None
            self.session.commit()
        except (IRPTransientError, IRPPermanentError) as exc:
            transient = isinstance(exc, IRPTransientError)
            exhausted = record.attempt_count >= record.max_attempts
            record.status = "RETRY" if transient and not exhausted else "DEAD"
            record.error_code = exc.code or type(exc).__name__
            record.error_text = str(exc)
            if record.status == "RETRY":
                delay = min(3600, 30 * (2 ** min(record.attempt_count - 1, 7)))
                record.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
            self.session.commit()
            logger.warning(
                "eway_bill_processing_failed",
                extra={"company_id": self.company_id, "record_id": record.id},
            )
        self.session.refresh(record)
        return record

    def list(self, *, limit: int = 100) -> tuple[EWayBill, ...]:
        """Return newest e-way bill records for operational review."""
        return tuple(
            self.session.scalars(
                select(EWayBill)
                .where(EWayBill.company_id == self.company_id, EWayBill.deleted_at.is_(None))
                .order_by(EWayBill.created_at.desc(), EWayBill.id)
                .limit(limit)
            )
        )

    def recover_stale_processing(
        self, *, now: datetime | None = None, stale_after: timedelta = timedelta(minutes=5)
    ) -> tuple[EWayBill, ...]:
        """Return interrupted e-way bill submissions to the retry queue."""
        current = now or datetime.now(UTC)
        records = tuple(
            self.session.scalars(
                select(EWayBill)
                .where(
                    EWayBill.company_id == self.company_id,
                    EWayBill.status == "PROCESSING",
                    EWayBill.last_attempt_at <= current - stale_after,
                    EWayBill.deleted_at.is_(None),
                )
                .with_for_update()
            )
        )
        for record in records:
            record.status = "RETRY"
            record.next_attempt_at = current
            record.error_code = "WORKER_INTERRUPTED"
            record.error_text = "The previous compliance worker stopped before completion."
        if records:
            self.session.commit()
        return records

    def _company(self) -> Company:
        company = self.session.scalar(
            select(Company).where(Company.id == self.company_id, Company.deleted_at.is_(None))
        )
        if company is None:
            raise EntityNotFoundError("Company was not found.")
        return company

    def _record(self, record_id: int, *, for_update: bool) -> EWayBill:
        statement = select(EWayBill).where(
            EWayBill.id == record_id,
            EWayBill.company_id == self.company_id,
            EWayBill.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        record = self.session.scalar(statement)
        if record is None:
            raise EntityNotFoundError("E-way bill was not found.")
        return record
