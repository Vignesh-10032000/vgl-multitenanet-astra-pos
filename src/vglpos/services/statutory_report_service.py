"""GST statutory reports built from immutable invoice and credit-note snapshots."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vglpos.domain.enums import SaleStatus
from vglpos.domain.models import (
    Company,
    CreditNote,
    CreditNoteItem,
    Customer,
    Product,
    Sale,
    SaleItem,
)
from vglpos.services.exceptions import EntityNotFoundError, ValidationError
from vglpos.utils.gst import uqc_code
from vglpos.utils.money import ZERO, money, qty

ZERO_QTY = Decimal("0.000")
DEFAULT_B2CL_THRESHOLD = Decimal("100000.00")
_REPORTABLE_STATUSES = (
    SaleStatus.COMPLETED.value,
    SaleStatus.PARTIALLY_RETURNED.value,
    SaleStatus.RETURNED.value,
)
_SERIES_PATTERN = re.compile(r"^(.*?)(\d+)(\D*)$")


@dataclass(frozen=True, slots=True)
class GstrTaxLine:
    rate: Decimal
    taxable_amount: Decimal
    igst_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    cess_amount: Decimal


@dataclass(frozen=True, slots=True)
class GstrInvoice:
    invoice_number: str
    invoice_date: date
    invoice_value: Decimal
    place_of_supply: str
    customer_gstin: str | None
    customer_name: str | None
    reverse_charge: bool
    invoice_type: str
    lines: tuple[GstrTaxLine, ...]


@dataclass(frozen=True, slots=True)
class GstrB2csRow:
    supply_type: str
    place_of_supply: str
    rate: Decimal
    taxable_amount: Decimal
    igst_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    cess_amount: Decimal


@dataclass(frozen=True, slots=True)
class GstrCreditNote:
    customer_gstin: str
    customer_name: str | None
    note_number: str
    note_date: date
    note_type: str
    place_of_supply: str
    note_value: Decimal
    lines: tuple[GstrTaxLine, ...]


@dataclass(frozen=True, slots=True)
class GstrHsnRow:
    hsn_code: str
    description: str
    uqc: str
    rate: Decimal
    total_quantity: Decimal
    total_value: Decimal
    taxable_amount: Decimal
    igst_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    cess_amount: Decimal


@dataclass(frozen=True, slots=True)
class GstrNilRow:
    supply_type: str
    nil_rated_amount: Decimal
    exempted_amount: Decimal
    non_gst_amount: Decimal


@dataclass(frozen=True, slots=True)
class DocumentIssuedRow:
    nature: str
    serial_from: str
    serial_to: str
    total_number: int
    cancelled: int
    net_issued: int


@dataclass(frozen=True, slots=True)
class Gstr1Report:
    gstin: str
    filing_period: str
    b2b: tuple[GstrInvoice, ...]
    b2cl: tuple[GstrInvoice, ...]
    b2cs: tuple[GstrB2csRow, ...]
    cdnr: tuple[GstrCreditNote, ...]
    nil: tuple[GstrNilRow, ...]
    hsn_b2b: tuple[GstrHsnRow, ...]
    hsn_b2c: tuple[GstrHsnRow, ...]
    credit_adjustments: tuple[RateWiseRow, ...]
    documents: tuple[DocumentIssuedRow, ...]


@dataclass(frozen=True, slots=True)
class Gstr3bSection:
    taxable_value: Decimal
    igst_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    cess_amount: Decimal


@dataclass(frozen=True, slots=True)
class Gstr3bReport:
    gstin: str
    filing_period: str
    outward_taxable: Gstr3bSection
    outward_zero_rated: Gstr3bSection
    outward_nil_exempt: Gstr3bSection
    inward_reverse_charge: Gstr3bSection
    non_gst_outward: Decimal


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    sale_id: int
    invoice_number: str
    issue: str
    expected_amount: Decimal
    actual_amount: Decimal
    difference: Decimal


@dataclass(frozen=True, slots=True)
class RateWiseRow:
    supply_type: str
    place_of_supply: str
    rate: Decimal
    taxable_amount: Decimal
    igst_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    cess_amount: Decimal


@dataclass(slots=True)
class _TaxAccumulator:
    taxable: Decimal = ZERO
    igst: Decimal = ZERO
    cgst: Decimal = ZERO
    sgst: Decimal = ZERO
    cess: Decimal = ZERO

    def add(
        self,
        *,
        taxable: Decimal,
        igst: Decimal,
        cgst: Decimal,
        sgst: Decimal,
        cess: Decimal,
        sign: Decimal = Decimal("1"),
    ) -> None:
        self.taxable = money(self.taxable + taxable * sign)
        self.igst = money(self.igst + igst * sign)
        self.cgst = money(self.cgst + cgst * sign)
        self.sgst = money(self.sgst + sgst * sign)
        self.cess = money(self.cess + cess * sign)

    def line(self, rate: Decimal) -> GstrTaxLine:
        return GstrTaxLine(
            rate=money(rate),
            taxable_amount=self.taxable,
            igst_amount=self.igst,
            cgst_amount=self.cgst,
            sgst_amount=self.sgst,
            cess_amount=self.cess,
        )


@dataclass(slots=True)
class _InvoiceAccumulator:
    sale: Sale
    gstin: str | None
    customer_name: str | None
    place_of_supply: str
    lines: dict[Decimal, _TaxAccumulator] = field(default_factory=dict)


@dataclass(slots=True)
class _NoteAccumulator:
    note: CreditNote
    gstin: str
    customer_name: str | None
    place_of_supply: str
    lines: dict[Decimal, _TaxAccumulator] = field(default_factory=dict)


@dataclass(slots=True)
class _HsnAccumulator:
    description: str
    quantity: Decimal = ZERO_QTY
    total_value: Decimal = ZERO
    tax: _TaxAccumulator = field(default_factory=_TaxAccumulator)


class StatutoryReportService:
    """Generate filing sections once so APIs and exported artifacts cannot diverge."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def gstr1(
        self,
        start_date: date,
        end_date: date,
        *,
        branch_id: int | None = None,
        b2cl_threshold: Decimal = DEFAULT_B2CL_THRESHOLD,
    ) -> Gstr1Report:
        """Build all outward-supply sections from the same immutable fact set."""
        self._validate_dates(start_date, end_date)
        if b2cl_threshold <= ZERO:
            raise ValidationError("B2C-large threshold must be positive.")
        company = self._company()
        if not company.gstin:
            raise ValidationError("Company GSTIN is required for statutory exports.")
        invoices, hsn = self._sales(start_date, end_date, company, branch_id)
        notes, credit_adjustments, b2cs_adjustments = self._credit_notes(
            start_date,
            end_date,
            company,
            branch_id,
            hsn,
            b2cl_threshold,
        )
        b2b: list[GstrInvoice] = []
        b2cl: list[GstrInvoice] = []
        b2cs_values: dict[tuple[str, str, Decimal], _TaxAccumulator] = {}
        nil_values: dict[str, Decimal] = {}
        for accumulator in invoices.values():
            taxable_lines = {
                rate: value for rate, value in accumulator.lines.items() if rate > ZERO
            }
            nil_amount = accumulator.lines.get(ZERO)
            if nil_amount is not None:
                nil_key = self._nil_supply_type(
                    registered=accumulator.gstin is not None,
                    interstate=accumulator.sale.supply_type == "INTERSTATE",
                )
                nil_values[nil_key] = money(nil_values.get(nil_key, ZERO) + nil_amount.taxable)
            if not taxable_lines:
                continue
            invoice = self._invoice(accumulator, taxable_lines)
            if accumulator.gstin is not None:
                b2b.append(invoice)
            elif (
                accumulator.sale.supply_type == "INTERSTATE"
                and accumulator.sale.net_amount > b2cl_threshold
            ):
                b2cl.append(invoice)
            else:
                for rate, amounts in taxable_lines.items():
                    key = (accumulator.sale.supply_type, accumulator.place_of_supply, rate)
                    target = b2cs_values.setdefault(key, _TaxAccumulator())
                    target.add(
                        taxable=amounts.taxable,
                        igst=amounts.igst,
                        cgst=amounts.cgst,
                        sgst=amounts.sgst,
                        cess=amounts.cess,
                    )
        for key, amounts in b2cs_adjustments.items():
            target = b2cs_values.setdefault(key, _TaxAccumulator())
            target.add(
                taxable=amounts.taxable,
                igst=amounts.igst,
                cgst=amounts.cgst,
                sgst=amounts.sgst,
                cess=amounts.cess,
                sign=Decimal("-1"),
            )
        b2cs = tuple(
            GstrB2csRow(
                supply_type=supply_type,
                place_of_supply=place_of_supply,
                rate=money(rate),
                taxable_amount=amounts.taxable,
                igst_amount=amounts.igst,
                cgst_amount=amounts.cgst,
                sgst_amount=amounts.sgst,
                cess_amount=amounts.cess,
            )
            for (supply_type, place_of_supply, rate), amounts in sorted(
                b2cs_values.items(), key=lambda item: item[0]
            )
        )
        hsn_b2b, hsn_b2c = self._hsn_rows(hsn)
        return Gstr1Report(
            gstin=company.gstin,
            filing_period=end_date.strftime("%m%Y"),
            b2b=tuple(sorted(b2b, key=lambda row: (row.invoice_date, row.invoice_number))),
            b2cl=tuple(sorted(b2cl, key=lambda row: (row.invoice_date, row.invoice_number))),
            b2cs=b2cs,
            cdnr=tuple(sorted(notes, key=lambda row: (row.note_date, row.note_number))),
            nil=tuple(
                GstrNilRow(key, value, ZERO, ZERO) for key, value in sorted(nil_values.items())
            ),
            hsn_b2b=hsn_b2b,
            hsn_b2c=hsn_b2c,
            credit_adjustments=credit_adjustments,
            documents=self._documents(start_date, end_date, branch_id),
        )

    def gstr3b(
        self, start_date: date, end_date: date, *, branch_id: int | None = None
    ) -> Gstr3bReport:
        """Summarise outward liability net of credit notes for GSTR-3B tables."""
        report = self.gstr1(start_date, end_date, branch_id=branch_id)
        taxable = _TaxAccumulator()
        nil_amount = money(sum((row.nil_rated_amount for row in report.nil), ZERO))
        for invoice in (*report.b2b, *report.b2cl):
            for line in invoice.lines:
                taxable.add(
                    taxable=line.taxable_amount,
                    igst=line.igst_amount,
                    cgst=line.cgst_amount,
                    sgst=line.sgst_amount,
                    cess=line.cess_amount,
                )
        for row in report.b2cs:
            taxable.add(
                taxable=row.taxable_amount,
                igst=row.igst_amount,
                cgst=row.cgst_amount,
                sgst=row.sgst_amount,
                cess=row.cess_amount,
            )
        for adjustment in report.credit_adjustments:
            taxable.add(
                taxable=adjustment.taxable_amount,
                igst=adjustment.igst_amount,
                cgst=adjustment.cgst_amount,
                sgst=adjustment.sgst_amount,
                cess=adjustment.cess_amount,
                sign=Decimal("-1"),
            )
        empty = Gstr3bSection(ZERO, ZERO, ZERO, ZERO, ZERO)
        return Gstr3bReport(
            gstin=report.gstin,
            filing_period=report.filing_period,
            outward_taxable=self._section(taxable),
            outward_zero_rated=empty,
            outward_nil_exempt=Gstr3bSection(nil_amount, ZERO, ZERO, ZERO, ZERO),
            inward_reverse_charge=empty,
            non_gst_outward=ZERO,
        )

    def reconciliation(
        self, start_date: date, end_date: date, *, branch_id: int | None = None
    ) -> tuple[ReconciliationIssue, ...]:
        """Flag header or line arithmetic drift before any statutory export is released."""
        self._validate_dates(start_date, end_date)
        statement = (
            select(
                Sale.id,
                Sale.invoice_number,
                Sale.taxable_amount,
                Sale.cgst_amount,
                Sale.sgst_amount,
                Sale.igst_amount,
                Sale.cess_amount,
                Sale.round_off,
                Sale.net_amount,
                func.coalesce(func.sum(SaleItem.taxable_amount), ZERO),
                func.coalesce(func.sum(SaleItem.cgst_amount), ZERO),
                func.coalesce(func.sum(SaleItem.sgst_amount), ZERO),
                func.coalesce(func.sum(SaleItem.igst_amount), ZERO),
                func.coalesce(func.sum(SaleItem.cess_amount), ZERO),
                func.coalesce(func.sum(SaleItem.total_amount), ZERO),
            )
            .join(SaleItem, SaleItem.sale_id == Sale.id)
            .where(
                Sale.company_id == self.company_id,
                SaleItem.company_id == self.company_id,
                Sale.business_date.between(start_date, end_date),
                Sale.deleted_at.is_(None),
                SaleItem.deleted_at.is_(None),
            )
            .group_by(Sale.id)
            .order_by(Sale.business_date, Sale.invoice_number)
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        issues: list[ReconciliationIssue] = []
        for row in self.session.execute(statement):
            header_components = money(row[2] + row[3] + row[4] + row[5] + row[6] + row[7])
            if header_components != money(row[8]):
                issues.append(
                    self._issue(row[0], row[1], "HEADER_COMPONENTS", header_components, row[8])
                )
            line_taxable = money(row[9])
            line_cgst = money(row[10])
            line_sgst = money(row[11])
            line_igst = money(row[12])
            line_cess = money(row[13])
            if (
                line_taxable != money(row[2])
                or line_cgst != money(row[3])
                or line_sgst != money(row[4])
                or line_igst != money(row[5])
                or line_cess != money(row[6])
            ):
                expected = money(row[2] + row[3] + row[4] + row[5] + row[6])
                actual = money(line_taxable + line_cgst + line_sgst + line_igst + line_cess)
                issues.append(self._issue(row[0], row[1], "HEADER_LINE_SUMS", expected, actual))
            expected_line_total = money(
                line_taxable + line_cgst + line_sgst + line_igst + line_cess
            )
            if expected_line_total != money(row[14]):
                issues.append(
                    self._issue(
                        row[0], row[1], "LINE_COMPONENTS", expected_line_total, money(row[14])
                    )
                )
        return tuple(issues)

    def hsn_register(
        self, start_date: date, end_date: date, *, branch_id: int | None = None
    ) -> tuple[GstrHsnRow, ...]:
        """Return the net HSN and rate register used by both GSTR-1 and the UI."""
        report = self.gstr1(start_date, end_date, branch_id=branch_id)
        return (*report.hsn_b2b, *report.hsn_b2c)

    def rate_register(
        self, start_date: date, end_date: date, *, branch_id: int | None = None
    ) -> tuple[RateWiseRow, ...]:
        """Aggregate taxable outward supplies by jurisdiction and stored invoice rate."""
        report = self.gstr1(start_date, end_date, branch_id=branch_id)
        values: dict[tuple[str, str, Decimal], _TaxAccumulator] = {}
        for invoice in (*report.b2b, *report.b2cl):
            supply_type = (
                "INTERSTATE"
                if any(line.igst_amount > ZERO for line in invoice.lines)
                else "INTRASTATE"
            )
            for line in invoice.lines:
                target = values.setdefault(
                    (supply_type, invoice.place_of_supply, line.rate), _TaxAccumulator()
                )
                target.add(
                    taxable=line.taxable_amount,
                    igst=line.igst_amount,
                    cgst=line.cgst_amount,
                    sgst=line.sgst_amount,
                    cess=line.cess_amount,
                )
        for row in report.b2cs:
            target = values.setdefault(
                (row.supply_type, row.place_of_supply, row.rate), _TaxAccumulator()
            )
            target.add(
                taxable=row.taxable_amount,
                igst=row.igst_amount,
                cgst=row.cgst_amount,
                sgst=row.sgst_amount,
                cess=row.cess_amount,
            )
        for adjustment in report.credit_adjustments:
            target = values.setdefault(
                (adjustment.supply_type, adjustment.place_of_supply, adjustment.rate),
                _TaxAccumulator(),
            )
            target.add(
                taxable=adjustment.taxable_amount,
                igst=adjustment.igst_amount,
                cgst=adjustment.cgst_amount,
                sgst=adjustment.sgst_amount,
                cess=adjustment.cess_amount,
                sign=Decimal("-1"),
            )
        return tuple(
            RateWiseRow(
                key[0],
                key[1],
                money(key[2]),
                value.taxable,
                value.igst,
                value.cgst,
                value.sgst,
                value.cess,
            )
            for key, value in sorted(values.items(), key=lambda item: item[0])
        )

    def _sales(
        self,
        start_date: date,
        end_date: date,
        company: Company,
        branch_id: int | None,
    ) -> tuple[
        dict[int, _InvoiceAccumulator], dict[tuple[bool, str, str, Decimal], _HsnAccumulator]
    ]:
        statement = (
            select(
                Sale,
                SaleItem,
                Product.name,
                Product.uom,
                Customer.gstin,
                Customer.name,
                Customer.state_code,
            )
            .join(SaleItem, SaleItem.sale_id == Sale.id)
            .join(Product, Product.id == SaleItem.product_id)
            .outerjoin(
                Customer,
                (Customer.id == Sale.customer_id)
                & (Customer.company_id == self.company_id)
                & Customer.deleted_at.is_(None),
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
            .order_by(Sale.business_date, Sale.invoice_number, SaleItem.line_number)
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        invoices: dict[int, _InvoiceAccumulator] = {}
        hsn: dict[tuple[bool, str, str, Decimal], _HsnAccumulator] = {}
        for (
            sale,
            item,
            product_name,
            product_uom,
            customer_gstin,
            customer_name,
            state_code,
        ) in self.session.execute(statement):
            gstin = (sale.customer_gstin_at_sale or customer_gstin or "").strip().upper() or None
            name = sale.customer_name_at_sale or customer_name
            place_of_supply = sale.place_of_supply or state_code or company.state_code
            invoice = invoices.setdefault(
                sale.id,
                _InvoiceAccumulator(sale, gstin, name, place_of_supply),
            )
            tax = invoice.lines.setdefault(money(item.tax_rate), _TaxAccumulator())
            tax.add(
                taxable=money(item.taxable_amount),
                igst=money(item.igst_amount),
                cgst=money(item.cgst_amount),
                sgst=money(item.sgst_amount),
                cess=money(item.cess_amount),
            )
            hsn_code = item.hsn_code_at_sale or "NA"
            unit = item.uqc_at_sale or uqc_code(product_uom)
            hsn_key = (gstin is not None, hsn_code, unit, money(item.tax_rate))
            summary = hsn.setdefault(hsn_key, _HsnAccumulator(product_name))
            summary.quantity = qty(summary.quantity + item.quantity)
            summary.total_value = money(summary.total_value + item.total_amount)
            summary.tax.add(
                taxable=money(item.taxable_amount),
                igst=money(item.igst_amount),
                cgst=money(item.cgst_amount),
                sgst=money(item.sgst_amount),
                cess=money(item.cess_amount),
            )
        return invoices, hsn

    def _credit_notes(
        self,
        start_date: date,
        end_date: date,
        company: Company,
        branch_id: int | None,
        hsn: dict[tuple[bool, str, str, Decimal], _HsnAccumulator],
        b2cl_threshold: Decimal,
    ) -> tuple[
        tuple[GstrCreditNote, ...],
        tuple[RateWiseRow, ...],
        dict[tuple[str, str, Decimal], _TaxAccumulator],
    ]:
        statement = (
            select(
                CreditNote,
                CreditNoteItem,
                Sale,
                SaleItem,
                Product.name,
                Product.uom,
                Customer.gstin,
                Customer.name,
                Customer.state_code,
            )
            .join(CreditNoteItem, CreditNoteItem.credit_note_id == CreditNote.id)
            .join(Sale, Sale.id == CreditNote.original_sale_id)
            .join(SaleItem, SaleItem.id == CreditNoteItem.original_sale_item_id)
            .join(Product, Product.id == SaleItem.product_id)
            .outerjoin(
                Customer,
                (Customer.id == Sale.customer_id)
                & (Customer.company_id == self.company_id)
                & Customer.deleted_at.is_(None),
            )
            .where(
                CreditNote.company_id == self.company_id,
                CreditNoteItem.company_id == self.company_id,
                Sale.company_id == self.company_id,
                SaleItem.company_id == self.company_id,
                Product.company_id == self.company_id,
                CreditNote.note_date.between(start_date, end_date),
                CreditNote.deleted_at.is_(None),
                CreditNoteItem.deleted_at.is_(None),
                Sale.deleted_at.is_(None),
                SaleItem.deleted_at.is_(None),
                Product.deleted_at.is_(None),
            )
            .order_by(CreditNote.note_date, CreditNote.credit_note_number, CreditNoteItem.id)
        )
        if branch_id is not None:
            statement = statement.where(CreditNote.branch_id == branch_id)
        notes: dict[int, _NoteAccumulator] = {}
        adjustments: dict[tuple[str, str, Decimal], _TaxAccumulator] = {}
        b2cs_adjustments: dict[tuple[str, str, Decimal], _TaxAccumulator] = {}
        for (
            note,
            note_item,
            sale,
            sale_item,
            product_name,
            product_uom,
            customer_gstin,
            customer_name,
            state_code,
        ) in self.session.execute(statement):
            gstin = (sale.customer_gstin_at_sale or customer_gstin or "").strip().upper()
            place_of_supply = sale.place_of_supply or state_code or company.state_code
            ratio = note_item.quantity / sale_item.quantity
            taxable = money(sale_item.taxable_amount * ratio)
            igst = money(sale_item.igst_amount * ratio)
            cgst = money(sale_item.cgst_amount * ratio)
            sgst = money(sale_item.sgst_amount * ratio)
            cess = money(sale_item.cess_amount * ratio)
            rate = money(sale_item.tax_rate)
            if gstin:
                accumulator = notes.setdefault(
                    note.id,
                    _NoteAccumulator(
                        note,
                        gstin,
                        sale.customer_name_at_sale or customer_name,
                        place_of_supply,
                    ),
                )
                tax = accumulator.lines.setdefault(rate, _TaxAccumulator())
                tax.add(taxable=taxable, igst=igst, cgst=cgst, sgst=sgst, cess=cess)
            adjustment_key = (sale.supply_type, place_of_supply, rate)
            is_b2cl = sale.supply_type == "INTERSTATE" and sale.net_amount > b2cl_threshold
            if gstin or is_b2cl:
                adjustment = adjustments.setdefault(adjustment_key, _TaxAccumulator())
                adjustment.add(
                    taxable=taxable,
                    igst=igst,
                    cgst=cgst,
                    sgst=sgst,
                    cess=cess,
                )
            else:
                b2cs_adjustment = b2cs_adjustments.setdefault(adjustment_key, _TaxAccumulator())
                b2cs_adjustment.add(
                    taxable=taxable,
                    igst=igst,
                    cgst=cgst,
                    sgst=sgst,
                    cess=cess,
                )
            hsn_code = sale_item.hsn_code_at_sale or "NA"
            unit = sale_item.uqc_at_sale or uqc_code(product_uom)
            hsn_key = (bool(gstin), hsn_code, unit, rate)
            summary = hsn.setdefault(hsn_key, _HsnAccumulator(product_name))
            summary.quantity = qty(summary.quantity - note_item.quantity)
            summary.total_value = money(summary.total_value - note_item.amount)
            summary.tax.add(
                taxable=taxable,
                igst=igst,
                cgst=cgst,
                sgst=sgst,
                cess=cess,
                sign=Decimal("-1"),
            )
        credit_notes = tuple(
            GstrCreditNote(
                customer_gstin=value.gstin,
                customer_name=value.customer_name,
                note_number=value.note.credit_note_number,
                note_date=value.note.note_date,
                note_type="C",
                place_of_supply=value.place_of_supply,
                note_value=money(value.note.net_amount),
                lines=tuple(amounts.line(rate) for rate, amounts in sorted(value.lines.items())),
            )
            for value in notes.values()
        )
        credit_adjustments = tuple(
            RateWiseRow(
                supply_type=key[0],
                place_of_supply=key[1],
                rate=key[2],
                taxable_amount=value.taxable,
                igst_amount=value.igst,
                cgst_amount=value.cgst,
                sgst_amount=value.sgst,
                cess_amount=value.cess,
            )
            for key, value in sorted(adjustments.items(), key=lambda item: item[0])
        )
        return credit_notes, credit_adjustments, b2cs_adjustments

    def _documents(
        self, start_date: date, end_date: date, branch_id: int | None
    ) -> tuple[DocumentIssuedRow, ...]:
        sale_statement = select(Sale.branch_id, Sale.invoice_number, Sale.sale_status).where(
            Sale.company_id == self.company_id,
            Sale.business_date.between(start_date, end_date),
            Sale.deleted_at.is_(None),
        )
        note_statement = select(CreditNote.branch_id, CreditNote.credit_note_number).where(
            CreditNote.company_id == self.company_id,
            CreditNote.note_date.between(start_date, end_date),
            CreditNote.deleted_at.is_(None),
        )
        if branch_id is not None:
            sale_statement = sale_statement.where(Sale.branch_id == branch_id)
            note_statement = note_statement.where(CreditNote.branch_id == branch_id)
        groups: dict[tuple[str, int, str], list[tuple[str, bool]]] = {}
        for row_branch, number, status in self.session.execute(sale_statement):
            key = ("Invoices for outward supply", row_branch, self._series(number))
            groups.setdefault(key, []).append((number, status == SaleStatus.CANCELLED.value))
        for row_branch, number in self.session.execute(note_statement):
            key = ("Credit Note", row_branch, self._series(number))
            groups.setdefault(key, []).append((number, False))
        rows = []
        for (nature, _row_branch, _series), documents in sorted(groups.items()):
            numbers = sorted(number for number, _cancelled in documents)
            cancelled = sum(1 for _number, is_cancelled in documents if is_cancelled)
            rows.append(
                DocumentIssuedRow(
                    nature=nature,
                    serial_from=numbers[0],
                    serial_to=numbers[-1],
                    total_number=len(numbers),
                    cancelled=cancelled,
                    net_issued=len(numbers) - cancelled,
                )
            )
        return tuple(rows)

    @staticmethod
    def _invoice(
        accumulator: _InvoiceAccumulator, lines: dict[Decimal, _TaxAccumulator]
    ) -> GstrInvoice:
        return GstrInvoice(
            invoice_number=accumulator.sale.invoice_number,
            invoice_date=accumulator.sale.business_date,
            invoice_value=money(accumulator.sale.net_amount),
            place_of_supply=accumulator.place_of_supply,
            customer_gstin=accumulator.gstin,
            customer_name=accumulator.customer_name,
            reverse_charge=False,
            invoice_type="Regular B2B",
            lines=tuple(amounts.line(rate) for rate, amounts in sorted(lines.items())),
        )

    @staticmethod
    def _hsn_rows(
        values: dict[tuple[bool, str, str, Decimal], _HsnAccumulator],
    ) -> tuple[tuple[GstrHsnRow, ...], tuple[GstrHsnRow, ...]]:
        b2b: list[GstrHsnRow] = []
        b2c: list[GstrHsnRow] = []
        for (registered, hsn_code, unit, rate), value in sorted(values.items()):
            row = GstrHsnRow(
                hsn_code=hsn_code,
                description=value.description,
                uqc=unit,
                rate=money(rate),
                total_quantity=qty(value.quantity),
                total_value=money(value.total_value),
                taxable_amount=value.tax.taxable,
                igst_amount=value.tax.igst,
                cgst_amount=value.tax.cgst,
                sgst_amount=value.tax.sgst,
                cess_amount=value.tax.cess,
            )
            (b2b if registered else b2c).append(row)
        return tuple(b2b), tuple(b2c)

    def _company(self) -> Company:
        company = self.session.scalar(
            select(Company).where(
                Company.id == self.company_id,
                Company.deleted_at.is_(None),
                Company.is_active.is_(True),
            )
        )
        if company is None:
            raise EntityNotFoundError("Company was not found.")
        return company

    @staticmethod
    def _section(value: _TaxAccumulator) -> Gstr3bSection:
        return Gstr3bSection(value.taxable, value.igst, value.cgst, value.sgst, value.cess)

    @staticmethod
    def _issue(
        sale_id: int, invoice_number: str, issue: str, expected: object, actual: object
    ) -> ReconciliationIssue:
        expected_amount = money(expected)
        actual_amount = money(actual)
        return ReconciliationIssue(
            sale_id=sale_id,
            invoice_number=invoice_number,
            issue=issue,
            expected_amount=expected_amount,
            actual_amount=actual_amount,
            difference=money(actual_amount - expected_amount),
        )

    @staticmethod
    def _nil_supply_type(*, registered: bool, interstate: bool) -> str:
        jurisdiction = "INTR" if interstate else "INTRA"
        return f"{jurisdiction}{'B2B' if registered else 'B2C'}"

    @staticmethod
    def _series(document_number: str) -> str:
        match = _SERIES_PATTERN.match(document_number)
        return f"{match.group(1)}*{match.group(3)}" if match is not None else document_number

    @staticmethod
    def _validate_dates(start_date: date, end_date: date) -> None:
        if start_date > end_date:
            raise ValidationError("Report start date cannot be after end date.")
