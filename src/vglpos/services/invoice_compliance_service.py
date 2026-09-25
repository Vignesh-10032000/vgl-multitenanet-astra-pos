"""Rule 46 invoice-template validation and company compliance controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.models import (
    Branch,
    Company,
    Customer,
    EInvoice,
    InvoiceTemplate,
    Product,
    Sale,
    SaleItem,
)
from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError

RULE46_FIELDS: frozenset[str] = frozenset(
    {
        "supplier_gstin",
        "supplier_legal_name",
        "supplier_address",
        "invoice_number",
        "invoice_date",
        "recipient_gstin_if_registered",
        "place_of_supply_if_interstate",
        "item_description",
        "hsn_code",
        "quantity",
        "uqc",
        "taxable_amount",
        "tax_rate",
        "tax_amount",
        "invoice_total",
        "composition_declaration_if_applicable",
    }
)


@dataclass(frozen=True, slots=True)
class ComplianceSettingsCommand:
    company_id: int
    user_id: int
    e_invoice_enabled: bool
    e_invoice_provider: str
    e_invoice_reporting_window_days: int
    e_invoice_retry_limit: int
    composition_scheme_enabled: bool
    composition_declaration: str
    invoice_validation_enabled: bool
    gst_filing_locked_through: date | None


@dataclass(frozen=True, slots=True)
class InvoiceTemplateCommand:
    company_id: int
    user_id: int
    code: str
    name: str
    paper_size: str
    mandatory_fields: tuple[str, ...] | list[str]
    declaration_text: str | None
    is_default: bool


class InvoiceComplianceService:
    """Keep fiscal issue/cancellation policy out of routes and checkout orchestration."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def settings(self) -> Company:
        """Return the tenant root carrying compliance policy."""
        return self._company()

    def configure(self, command: ComplianceSettingsCommand) -> Company:
        """Update coupled compliance controls atomically after cross-field validation."""
        if command.company_id != self.company_id or not command.user_id:
            raise ValidationError("Authenticated company and user are required.")
        if command.e_invoice_provider.strip().upper() != "NIC":
            raise ValidationError("NIC is the only configured Phase 9 IRP adapter.")
        if not 1 <= command.e_invoice_reporting_window_days <= 365:
            raise ValidationError("E-invoice reporting window must be between 1 and 365 days.")
        if not 1 <= command.e_invoice_retry_limit <= 20:
            raise ValidationError("E-invoice retry limit must be between 1 and 20.")
        if command.e_invoice_enabled and command.composition_scheme_enabled:
            raise ValidationError("Composition taxpayers cannot enable e-invoice generation.")
        if command.composition_scheme_enabled and not command.composition_declaration.strip():
            raise ValidationError("Composition mode requires the statutory declaration.")
        company = self._company(for_update=True)
        company.e_invoice_enabled = command.e_invoice_enabled
        company.e_invoice_provider = command.e_invoice_provider.strip().upper()
        company.e_invoice_reporting_window_days = command.e_invoice_reporting_window_days
        company.e_invoice_retry_limit = command.e_invoice_retry_limit
        company.composition_scheme_enabled = command.composition_scheme_enabled
        company.composition_declaration = command.composition_declaration.strip()
        company.invoice_validation_enabled = command.invoice_validation_enabled
        company.gst_filing_locked_through = command.gst_filing_locked_through
        company.updated_by = command.user_id
        company.row_version += 1
        self.session.commit()
        self.session.refresh(company)
        return company

    def create_template(self, command: InvoiceTemplateCommand) -> InvoiceTemplate:
        """Create a reviewed Rule 46 policy without accepting unknown validation fields."""
        if command.company_id != self.company_id or not command.user_id:
            raise ValidationError("Authenticated company and user are required.")
        code = command.code.strip().upper()
        name = command.name.strip()
        paper_size = command.paper_size.strip().upper()
        fields = tuple(dict.fromkeys(command.mandatory_fields))
        unknown = sorted(set(fields) - RULE46_FIELDS)
        if not code or not name:
            raise ValidationError("Template code and name are required.")
        if paper_size not in {"58", "80", "A5"}:
            raise ValidationError("Template paper size must be 58, 80, or A5.")
        if unknown:
            raise ValidationError(f"Unsupported Rule 46 fields: {', '.join(unknown)}.")
        if not fields:
            raise ValidationError("At least one Rule 46 field is required.")
        if command.is_default:
            self.session.execute(
                update(InvoiceTemplate)
                .where(
                    InvoiceTemplate.company_id == self.company_id,
                    InvoiceTemplate.deleted_at.is_(None),
                    InvoiceTemplate.is_default.is_(True),
                )
                .values(is_default=False, updated_by=command.user_id)
            )
        template = InvoiceTemplate(
            company_id=self.company_id,
            code=code,
            name=name,
            paper_size=paper_size,
            mandatory_fields=list(fields),
            declaration_text=(
                command.declaration_text.strip() if command.declaration_text else None
            ),
            is_default=command.is_default,
            created_by=command.user_id,
        )
        self.session.add(template)
        try:
            self.session.commit()
            self.session.refresh(template)
            return template
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Invoice template code already exists.") from exc

    def templates(self) -> tuple[InvoiceTemplate, ...]:
        """List active templates with the default first."""
        return tuple(
            self.session.scalars(
                select(InvoiceTemplate)
                .where(
                    InvoiceTemplate.company_id == self.company_id,
                    InvoiceTemplate.deleted_at.is_(None),
                    InvoiceTemplate.is_active.is_(True),
                )
                .order_by(InvoiceTemplate.is_default.desc(), InvoiceTemplate.code)
            )
        )

    def validate_before_issue(
        self,
        *,
        company: Company,
        branch: Branch,
        sale: Sale,
        customer: Customer | None,
        items: tuple[SaleItem, ...],
        products: dict[int, Product],
    ) -> None:
        """Fail checkout before commit when an enabled template lacks mandatory invoice facts."""
        if not company.invoice_validation_enabled:
            return
        template = self.session.scalar(
            select(InvoiceTemplate)
            .where(
                InvoiceTemplate.company_id == self.company_id,
                InvoiceTemplate.deleted_at.is_(None),
                InvoiceTemplate.is_active.is_(True),
                InvoiceTemplate.is_default.is_(True),
            )
            .order_by(InvoiceTemplate.id)
            .limit(1)
        )
        fields = set(template.mandatory_fields if template is not None else RULE46_FIELDS)
        missing: list[str] = []
        supplier_gstin = branch.gstin or company.gstin
        tax_amount = sale.cgst_amount + sale.sgst_amount + sale.igst_amount + sale.cess_amount
        checks: dict[str, bool] = {
            "supplier_gstin": bool(supplier_gstin),
            "supplier_legal_name": bool(company.legal_name.strip()),
            "supplier_address": bool(branch.address_line1.strip() and branch.postal_code.strip()),
            "invoice_number": bool(sale.invoice_number.strip()),
            "invoice_date": bool(sale.business_date),
            "recipient_gstin_if_registered": bool(
                customer is None or customer.gstin is None or customer.gstin.strip()
            ),
            "place_of_supply_if_interstate": bool(
                sale.supply_type != "INTERSTATE" or sale.place_of_supply
            ),
            "item_description": bool(
                items
                and all(
                    products.get(item.product_id) and products[item.product_id].name
                    for item in items
                )
            ),
            "hsn_code": bool(items and all(item.hsn_code_at_sale for item in items)),
            "quantity": bool(items and all(item.quantity > 0 for item in items)),
            "uqc": bool(items and all(item.uqc_at_sale for item in items)),
            "taxable_amount": sale.taxable_amount >= 0,
            "tax_rate": bool(items and all(item.tax_rate >= 0 for item in items)),
            "tax_amount": tax_amount >= 0,
            "invoice_total": sale.net_amount >= 0,
            "composition_declaration_if_applicable": bool(
                not company.composition_scheme_enabled or company.composition_declaration.strip()
            ),
        }
        for field in sorted(fields):
            if not checks.get(field, False):
                missing.append(field)
        if missing:
            raise ValidationError(
                "Invoice cannot be issued; mandatory Rule 46 fields are missing: "
                + ", ".join(missing)
                + "."
            )

    def enforce_sale_cancellation(self, sale: Sale, *, now: datetime | None = None) -> None:
        """Permit local cancellation only on issue day, before filing and after IRN cancellation."""
        current = now or datetime.now(UTC)
        created_at = sale.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if created_at.astimezone(UTC).date() != current.astimezone(UTC).date():
            raise ConflictError("Invoices can only be cancelled on the day they were issued.")
        company = self._company()
        if (
            company.gst_filing_locked_through is not None
            and sale.business_date <= company.gst_filing_locked_through
        ):
            raise ConflictError(
                "The invoice belongs to a filed GST period and cannot be cancelled."
            )
        record = self.session.scalar(
            select(EInvoice).where(
                EInvoice.company_id == self.company_id,
                EInvoice.sale_id == sale.id,
                EInvoice.deleted_at.is_(None),
            )
        )
        if record is not None and record.status not in {"CANCELLED", "DEAD"}:
            raise ConflictError("Cancel the IRN before cancelling this invoice.")

    def _company(self, *, for_update: bool = False) -> Company:
        statement = select(Company).where(
            Company.id == self.company_id, Company.deleted_at.is_(None)
        )
        if for_update:
            statement = statement.with_for_update()
        company = self.session.scalar(statement)
        if company is None:
            raise EntityNotFoundError("Company was not found.")
        return company
