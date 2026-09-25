"""Deterministic GST, spreadsheet, and Tally artifact encoders."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import cast
from xml.etree import ElementTree
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import (
    Company,
    CreditNote,
    Customer,
    Purchase,
    PurchaseReturn,
    Sale,
    Supplier,
    SupplierLedger,
)
from vglpos.services.exceptions import EntityNotFoundError, ValidationError
from vglpos.services.statutory_report_service import (
    DocumentIssuedRow,
    Gstr1Report,
    GstrCreditNote,
    GstrHsnRow,
    GstrInvoice,
    GstrTaxLine,
)
from vglpos.utils.gst import STATE_CODES
from vglpos.utils.money import ZERO, money

type JsonScalar = str | int | bool | Decimal | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type CellValue = str | int | bool | Decimal | None

_UQC_LABELS: dict[str, str] = {
    "BAG": "BAG-BAGS",
    "BAL": "BAL-BALE",
    "BDL": "BDL-BUNDLES",
    "BOX": "BOX-BOX",
    "CTN": "CTN-CARTONS",
    "DOZ": "DOZ-DOZENS",
    "GMS": "GMS-GRAMMES",
    "KGS": "KGS-KILOGRAMS",
    "LTR": "LTR-LITRES",
    "MLT": "MLT-MILLILITRES",
    "MTR": "MTR-METERS",
    "NOS": "NOS-NUMBERS",
    "OTH": "OTH-OTHERS",
    "PAC": "PAC-PACKS",
    "PRS": "PRS-PAIRS",
    "SET": "SET-SETS",
    "TON": "TON-TONNES",
}


class ReportExportService:
    """Encode service-layer report facts without re-querying different totals."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def gstr1_government_payload(self, report: Gstr1Report) -> dict[str, JsonValue]:
        """Map a complete GSTR-1 report to the GST Save GSTR-1 request shape."""
        b2b_groups: dict[str, list[JsonValue]] = {}
        for invoice in report.b2b:
            assert invoice.customer_gstin is not None
            b2b_groups.setdefault(invoice.customer_gstin, []).append(self._invoice_payload(invoice))
        b2cl_groups: dict[str, list[JsonValue]] = {}
        for invoice in report.b2cl:
            b2cl_groups.setdefault(invoice.place_of_supply, []).append(
                self._invoice_payload(invoice, include_pos=False)
            )
        cdnr_groups: dict[str, list[JsonValue]] = {}
        for note in report.cdnr:
            cdnr_groups.setdefault(note.customer_gstin, []).append(self._note_payload(note))
        return {
            "gstin": report.gstin,
            "fp": report.filing_period,
            "b2b": [
                {"ctin": gstin, "inv": invoices} for gstin, invoices in sorted(b2b_groups.items())
            ],
            "b2cl": [
                {"pos": place_of_supply, "inv": invoices}
                for place_of_supply, invoices in sorted(b2cl_groups.items())
            ],
            "b2cs": [
                {
                    "sply_ty": "INTER" if row.supply_type == "INTERSTATE" else "INTRA",
                    "pos": row.place_of_supply,
                    "typ": "OE",
                    "rt": row.rate,
                    "txval": row.taxable_amount,
                    "iamt": row.igst_amount,
                    "camt": row.cgst_amount,
                    "samt": row.sgst_amount,
                    "csamt": row.cess_amount,
                }
                for row in report.b2cs
            ],
            "cdnr": [{"ctin": gstin, "nt": notes} for gstin, notes in sorted(cdnr_groups.items())],
            "nil": {
                "inv": [
                    {
                        "sply_ty": row.supply_type,
                        "nil_amt": row.nil_rated_amount,
                        "expt_amt": row.exempted_amount,
                        "ngsup_amt": row.non_gst_amount,
                    }
                    for row in report.nil
                ]
            },
            "hsn": {
                "hsn_b2b": self._hsn_payload(report.hsn_b2b),
                "hsn_b2c": self._hsn_payload(report.hsn_b2c),
            },
            "doc_issue": {"doc_det": self._document_payload(report.documents)},
        }

    def gstr1_json(self, report: Gstr1Report) -> bytes:
        """Serialize government JSON with Decimal values emitted as numeric tokens."""
        payload = self.gstr1_government_payload(report)
        return (decimal_json_dumps(payload, indent=2) + "\n").encode("utf-8")

    def gstr1_offline_xlsx(self, report: Gstr1Report) -> bytes:
        """Create section sheets using the official Returns Offline Tool headers."""
        sheets = (
            (
                "b2b,sez,de",
                "Summary For B2B, SEZ, DE (4A, 4B, 6B, 6C)",
                (
                    "GSTIN/UIN of Recipient",
                    "Receiver Name",
                    "Invoice Number",
                    "Invoice date",
                    "Invoice Value",
                    "Place Of Supply",
                    "Reverse Charge",
                    "Applicable % of Tax Rate",
                    "Invoice Type",
                    "E-Commerce GSTIN",
                    "Rate",
                    "Taxable Value",
                    "Cess Amount",
                ),
                self._b2b_rows(report.b2b),
            ),
            (
                "b2cl",
                "Summary For B2CL (5)",
                (
                    "Invoice Number",
                    "Invoice date",
                    "Invoice Value",
                    "Place Of Supply",
                    "Applicable % of Tax Rate",
                    "Rate",
                    "Taxable Value",
                    "Cess Amount",
                    "E-Commerce GSTIN",
                ),
                self._b2cl_rows(report.b2cl),
            ),
            (
                "b2cs",
                "Summary For B2CS (7)",
                (
                    "Type",
                    "Place Of Supply",
                    "Rate",
                    "Applicable % of Tax Rate",
                    "Taxable Value",
                    "Cess Amount",
                    "E-Commerce GSTIN",
                ),
                tuple(
                    (
                        "OE",
                        self._place(row.place_of_supply),
                        row.rate,
                        None,
                        row.taxable_amount,
                        row.cess_amount,
                        None,
                    )
                    for row in report.b2cs
                ),
            ),
            (
                "cdnr",
                "Summary For CDNR (9B)",
                (
                    "GSTIN/UIN of Recipient",
                    "Receiver Name",
                    "Note Number",
                    "Note Date",
                    "Note Type",
                    "Place Of Supply",
                    "Reverse Charge",
                    "Note Supply Type",
                    "Note Value",
                    "Applicable % of Tax Rate",
                    "Rate",
                    "Taxable Value",
                    "Cess Amount",
                ),
                self._cdnr_rows(report.cdnr),
            ),
            self._hsn_sheet("hsn(b2b)", "Summary For HSN B2B (12)", report.hsn_b2b),
            self._hsn_sheet("hsn(b2c)", "Summary For HSN B2C (12)", report.hsn_b2c),
            (
                "docs",
                "Summary of documents issued during the tax period (13)",
                ("Nature of Document", "Sr. No. From", "Sr. No. To", "Total Number", "Cancelled"),
                tuple(
                    (
                        row.nature,
                        row.serial_from,
                        row.serial_to,
                        row.total_number,
                        row.cancelled,
                    )
                    for row in report.documents
                ),
            ),
        )
        return xlsx_bytes(sheets)

    def tally_xml(self, start_date: date, end_date: date, *, branch_id: int | None = None) -> bytes:
        """Export tenant sales, purchases, and payable adjustments as Tally vouchers."""
        if start_date > end_date:
            raise ValidationError("Report start date cannot be after end date.")
        company = self._company()
        root = ElementTree.Element("ENVELOPE")
        header = ElementTree.SubElement(root, "HEADER")
        ElementTree.SubElement(header, "TALLYREQUEST").text = "Import Data"
        body = ElementTree.SubElement(root, "BODY")
        import_data = ElementTree.SubElement(body, "IMPORTDATA")
        request_desc = ElementTree.SubElement(import_data, "REQUESTDESC")
        ElementTree.SubElement(request_desc, "REPORTNAME").text = "Vouchers"
        static = ElementTree.SubElement(request_desc, "STATICVARIABLES")
        ElementTree.SubElement(static, "SVCURRENTCOMPANY").text = company.legal_name
        request_data = ElementTree.SubElement(import_data, "REQUESTDATA")
        self._tally_sales(request_data, start_date, end_date, branch_id)
        self._tally_purchases(request_data, start_date, end_date, branch_id)
        self._tally_journals(request_data, start_date, end_date, branch_id)
        return cast(bytes, ElementTree.tostring(root, encoding="utf-8", xml_declaration=True))

    @staticmethod
    def _invoice_payload(invoice: GstrInvoice, *, include_pos: bool = True) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "inum": invoice.invoice_number,
            "idt": invoice.invoice_date.strftime("%d-%m-%Y"),
            "val": invoice.invoice_value,
            "rchrg": "Y" if invoice.reverse_charge else "N",
            "inv_typ": "R",
            "itms": ReportExportService._items_payload(invoice.lines),
        }
        if include_pos:
            payload["pos"] = invoice.place_of_supply
        return payload

    @staticmethod
    def _note_payload(note: GstrCreditNote) -> dict[str, JsonValue]:
        return {
            "ntty": note.note_type,
            "nt_num": note.note_number,
            "nt_dt": note.note_date.strftime("%d-%m-%Y"),
            "val": note.note_value,
            "pos": note.place_of_supply,
            "rchrg": "N",
            "inv_typ": "R",
            "itms": ReportExportService._items_payload(note.lines),
        }

    @staticmethod
    def _items_payload(lines: Sequence[GstrTaxLine]) -> list[JsonValue]:
        return [
            {
                "num": index,
                "itm_det": {
                    "rt": line.rate,
                    "txval": line.taxable_amount,
                    "iamt": line.igst_amount,
                    "camt": line.cgst_amount,
                    "samt": line.sgst_amount,
                    "csamt": line.cess_amount,
                },
            }
            for index, line in enumerate(lines, start=1)
        ]

    @staticmethod
    def _hsn_payload(rows: Sequence[GstrHsnRow]) -> list[JsonValue]:
        return [
            {
                "num": index,
                "hsn_sc": row.hsn_code,
                "desc": row.description,
                "uqc": row.uqc,
                "qty": row.total_quantity,
                "val": row.total_value,
                "rt": row.rate,
                "txval": row.taxable_amount,
                "iamt": row.igst_amount,
                "camt": row.cgst_amount,
                "samt": row.sgst_amount,
                "csamt": row.cess_amount,
            }
            for index, row in enumerate(rows, start=1)
        ]

    @staticmethod
    def _document_payload(rows: Sequence[DocumentIssuedRow]) -> list[JsonValue]:
        codes = {"Invoices for outward supply": 1, "Credit Note": 4}
        return [
            {
                "doc_num": codes.get(row.nature, 12),
                "docs": [
                    {
                        "num": 1,
                        "from": row.serial_from,
                        "to": row.serial_to,
                        "totnum": row.total_number,
                        "cancel": row.cancelled,
                        "net_issue": row.net_issued,
                    }
                ],
            }
            for row in rows
        ]

    def _b2b_rows(self, invoices: Sequence[GstrInvoice]) -> tuple[tuple[CellValue, ...], ...]:
        rows = []
        for invoice in invoices:
            for line in invoice.lines:
                rows.append(
                    (
                        invoice.customer_gstin,
                        invoice.customer_name,
                        invoice.invoice_number,
                        invoice.invoice_date.strftime("%d-%b-%y"),
                        invoice.invoice_value,
                        self._place(invoice.place_of_supply),
                        "Y" if invoice.reverse_charge else "N",
                        None,
                        invoice.invoice_type,
                        None,
                        line.rate,
                        line.taxable_amount,
                        line.cess_amount,
                    )
                )
        return tuple(rows)

    def _b2cl_rows(self, invoices: Sequence[GstrInvoice]) -> tuple[tuple[CellValue, ...], ...]:
        rows = []
        for invoice in invoices:
            for line in invoice.lines:
                rows.append(
                    (
                        invoice.invoice_number,
                        invoice.invoice_date.strftime("%d-%b-%y"),
                        invoice.invoice_value,
                        self._place(invoice.place_of_supply),
                        None,
                        line.rate,
                        line.taxable_amount,
                        line.cess_amount,
                        None,
                    )
                )
        return tuple(rows)

    def _cdnr_rows(self, notes: Sequence[GstrCreditNote]) -> tuple[tuple[CellValue, ...], ...]:
        rows = []
        for note in notes:
            for line in note.lines:
                rows.append(
                    (
                        note.customer_gstin,
                        note.customer_name,
                        note.note_number,
                        note.note_date.strftime("%d-%b-%y"),
                        note.note_type,
                        self._place(note.place_of_supply),
                        "N",
                        "Regular B2B",
                        note.note_value,
                        None,
                        line.rate,
                        line.taxable_amount,
                        line.cess_amount,
                    )
                )
        return tuple(rows)

    @staticmethod
    def _hsn_sheet(
        name: str, title: str, rows: Sequence[GstrHsnRow]
    ) -> tuple[str, str, tuple[str, ...], tuple[tuple[CellValue, ...], ...]]:
        headers = (
            "HSN",
            "Description",
            "UQC",
            "Total Quantity",
            "Total Value",
            "Taxable Value",
            "Integrated Tax Amount",
            "Central Tax Amount",
            "State/UT Tax Amount",
            "Cess Amount",
            "Rate",
        )
        data = tuple(
            (
                row.hsn_code,
                row.description,
                _UQC_LABELS.get(row.uqc, "OTH-OTHERS"),
                row.total_quantity,
                row.total_value,
                row.taxable_amount,
                row.igst_amount,
                row.cgst_amount,
                row.sgst_amount,
                row.cess_amount,
                row.rate,
            )
            for row in rows
        )
        return name, title, headers, data

    @staticmethod
    def _place(state_code: str) -> str:
        return f"{state_code}-{STATE_CODES.get(state_code, 'Unknown')}"

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

    def _tally_sales(
        self, parent: ElementTree.Element, start_date: date, end_date: date, branch_id: int | None
    ) -> None:
        statement = (
            select(Sale, Customer.name)
            .outerjoin(
                Customer,
                (Customer.id == Sale.customer_id)
                & (Customer.company_id == self.company_id)
                & Customer.deleted_at.is_(None),
            )
            .where(
                Sale.company_id == self.company_id,
                Sale.business_date.between(start_date, end_date),
                Sale.sale_status.in_(("COMPLETED", "PARTIALLY_RETURNED", "RETURNED")),
                Sale.deleted_at.is_(None),
            )
            .order_by(Sale.business_date, Sale.invoice_number)
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        for sale, customer_name in self.session.execute(statement):
            party = sale.customer_name_at_sale or customer_name or "Cash"
            self._voucher(
                parent,
                voucher_type="Sales",
                number=sale.invoice_number,
                voucher_date=sale.business_date,
                narration="VGL POS tax invoice",
                entries=(
                    (party, -money(sale.net_amount)),
                    ("Sales", money(sale.taxable_amount)),
                    ("Output CGST", money(sale.cgst_amount)),
                    ("Output SGST", money(sale.sgst_amount)),
                    ("Output IGST", money(sale.igst_amount)),
                    ("Output Cess", money(sale.cess_amount)),
                    ("Round Off", money(sale.round_off)),
                ),
            )

    def _tally_purchases(
        self, parent: ElementTree.Element, start_date: date, end_date: date, branch_id: int | None
    ) -> None:
        statement = (
            select(Purchase, Supplier.name)
            .join(
                Supplier,
                (Supplier.id == Purchase.supplier_id) & (Supplier.company_id == self.company_id),
            )
            .where(
                Purchase.company_id == self.company_id,
                Purchase.invoice_date.between(start_date, end_date),
                Purchase.deleted_at.is_(None),
                Supplier.deleted_at.is_(None),
            )
            .order_by(Purchase.invoice_date, Purchase.invoice_number)
        )
        if branch_id is not None:
            statement = statement.where(Purchase.branch_id == branch_id)
        for purchase, supplier_name in self.session.execute(statement):
            self._voucher(
                parent,
                voucher_type="Purchase",
                number=purchase.invoice_number,
                voucher_date=purchase.invoice_date,
                narration="VGL POS supplier invoice",
                entries=(
                    (supplier_name, money(purchase.total_amount)),
                    ("Purchases", -money(purchase.taxable_amount + purchase.landed_cost_amount)),
                    ("Input CGST", -money(purchase.cgst_amount)),
                    ("Input SGST", -money(purchase.sgst_amount)),
                    ("Input IGST", -money(purchase.igst_amount)),
                    ("Input Cess", -money(purchase.cess_amount)),
                ),
            )

    def _tally_journals(
        self, parent: ElementTree.Element, start_date: date, end_date: date, branch_id: int | None
    ) -> None:
        note_statement = select(CreditNote).where(
            CreditNote.company_id == self.company_id,
            CreditNote.note_date.between(start_date, end_date),
            CreditNote.deleted_at.is_(None),
        )
        return_statement = (
            select(PurchaseReturn, Supplier.name)
            .join(
                Supplier,
                (Supplier.id == PurchaseReturn.supplier_id)
                & (Supplier.company_id == self.company_id),
            )
            .where(
                PurchaseReturn.company_id == self.company_id,
                PurchaseReturn.return_date.between(start_date, end_date),
                PurchaseReturn.deleted_at.is_(None),
                Supplier.deleted_at.is_(None),
            )
        )
        if branch_id is not None:
            note_statement = note_statement.where(CreditNote.branch_id == branch_id)
            return_statement = return_statement.where(PurchaseReturn.branch_id == branch_id)
        for note in self.session.scalars(note_statement.order_by(CreditNote.note_date)):
            self._voucher(
                parent,
                voucher_type="Journal",
                number=note.credit_note_number,
                voucher_date=note.note_date,
                narration="Sales credit note",
                entries=(
                    ("Sales Returns", -money(note.net_amount)),
                    ("Customer Returns", money(note.net_amount)),
                ),
            )
        for purchase_return, supplier_name in self.session.execute(
            return_statement.order_by(PurchaseReturn.return_date)
        ):
            self._voucher(
                parent,
                voucher_type="Journal",
                number=purchase_return.debit_note_number,
                voucher_date=purchase_return.return_date,
                narration="Purchase debit note",
                entries=(
                    (supplier_name, -money(purchase_return.total_amount)),
                    ("Purchase Returns", money(purchase_return.total_amount)),
                ),
            )
        payments = (
            select(SupplierLedger, Supplier.name)
            .join(
                Supplier,
                (Supplier.id == SupplierLedger.supplier_id)
                & (Supplier.company_id == self.company_id),
            )
            .where(
                SupplierLedger.company_id == self.company_id,
                SupplierLedger.txn_date.between(start_date, end_date),
                SupplierLedger.txn_type == "PAYMENT",
                SupplierLedger.deleted_at.is_(None),
                Supplier.deleted_at.is_(None),
            )
        )
        for movement, supplier_name in self.session.execute(payments.order_by(SupplierLedger.id)):
            self._voucher(
                parent,
                voucher_type="Journal",
                number=movement.reference_id,
                voucher_date=movement.txn_date,
                narration=movement.notes or "Supplier payment",
                entries=(
                    (supplier_name, -money(movement.debit_amount)),
                    ("Bank", money(movement.debit_amount)),
                ),
            )

    @staticmethod
    def _voucher(
        parent: ElementTree.Element,
        *,
        voucher_type: str,
        number: str,
        voucher_date: date,
        narration: str,
        entries: Sequence[tuple[str, Decimal]],
    ) -> None:
        message = ElementTree.SubElement(parent, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        voucher = ElementTree.SubElement(
            message, "VOUCHER", {"VCHTYPE": voucher_type, "ACTION": "Create"}
        )
        ElementTree.SubElement(voucher, "DATE").text = voucher_date.strftime("%Y%m%d")
        ElementTree.SubElement(voucher, "VOUCHERTYPENAME").text = voucher_type
        ElementTree.SubElement(voucher, "VOUCHERNUMBER").text = number
        ElementTree.SubElement(voucher, "NARRATION").text = narration
        for ledger_name, amount in entries:
            if amount == ZERO:
                continue
            entry = ElementTree.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ElementTree.SubElement(entry, "LEDGERNAME").text = ledger_name
            ElementTree.SubElement(entry, "ISDEEMEDPOSITIVE").text = (
                "Yes" if amount < ZERO else "No"
            )
            ElementTree.SubElement(entry, "AMOUNT").text = format(amount, "f")


def decimal_json_dumps(value: JsonValue, *, indent: int | None = None) -> str:
    """Serialize a JSON tree while refusing binary floating-point values."""

    def encode(node: JsonValue, level: int) -> str:
        if node is None:
            return "null"
        if isinstance(node, bool):
            return "true" if node else "false"
        if isinstance(node, Decimal):
            if not node.is_finite():
                raise ValueError("Non-finite Decimal cannot be serialized as JSON.")
            return format(node, "f")
        if isinstance(node, int):
            return str(node)
        if isinstance(node, str):
            return json.dumps(node, ensure_ascii=False)
        if isinstance(node, list):
            if not node:
                return "[]"
            if indent is None:
                return "[" + ",".join(encode(item, level + 1) for item in node) + "]"
            padding = " " * (indent * (level + 1))
            closing = " " * (indent * level)
            return (
                "[\n"
                + padding
                + (",\n" + padding).join(encode(item, level + 1) for item in node)
                + "\n"
                + closing
                + "]"
            )
        if isinstance(node, dict):
            if not node:
                return "{}"
            separator = ": " if indent is not None else ":"
            parts = [
                f"{json.dumps(key, ensure_ascii=False)}{separator}{encode(item, level + 1)}"
                for key, item in node.items()
            ]
            if indent is None:
                return "{" + ",".join(parts) + "}"
            padding = " " * (indent * (level + 1))
            closing = " " * (indent * level)
            return "{\n" + padding + (",\n" + padding).join(parts) + "\n" + closing + "}"
        raise TypeError(f"Unsupported JSON value: {type(node).__name__}.")

    return encode(value, 0)


def xlsx_bytes(
    sheets: Sequence[tuple[str, str, Sequence[str], Sequence[Sequence[CellValue]]]],
) -> bytes:
    """Write the small OOXML subset required by the GST offline workbook importer."""
    if not sheets:
        raise ValueError("At least one worksheet is required.")
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types(len(sheets)))
        archive.writestr("_rels/.rels", _root_relationships())
        archive.writestr("xl/workbook.xml", _workbook(sheets))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships(len(sheets)))
        archive.writestr("xl/styles.xml", _styles())
        for index, (_name, title, headers, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet(title, headers, rows))
    return stream.getvalue()


def _content_types(sheet_count: int) -> str:
    sheets = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.spreadsheetml.styles+xml"/>'
        f"{sheets}</Types>"
    )


def _root_relationships() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook(
    sheets: Sequence[tuple[str, str, Sequence[str], Sequence[Sequence[CellValue]]]],
) -> str:
    entries = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _title, _headers, _rows) in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{entries}</sheets></workbook>"
    )


def _workbook_relationships(sheet_count: int) -> str:
    entries = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{entries}"
        f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )


def _styles() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/>'
        '<color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill '
        'patternType="gray125"/></fill><fill><patternFill patternType="solid">'
        '<fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        "</cellStyleXfs>"
        '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" '
        'xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" '
        'applyFill="1" applyFont="1"/><xf numFmtId="2" fontId="0" fillId="0" '
        'borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="4" fontId="0" '
        'fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )


def _worksheet(title: str, headers: Sequence[str], rows: Sequence[Sequence[CellValue]]) -> str:
    all_rows: list[Sequence[CellValue]] = [(title,), ("No. of Records", len(rows)), headers, *rows]
    row_xml = []
    for row_number, row in enumerate(all_rows, start=1):
        cells = "".join(
            _cell(_column_name(column_number), row_number, value, header=row_number == 3)
            for column_number, value in enumerate(row, start=1)
        )
        row_xml.append(f'<row r="{row_number}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{_column_name(max(1, len(headers)))}{len(all_rows)}"/>'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="3" topLeftCell="A4" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/><sheetData>'
        + "".join(row_xml)
        + '</sheetData><autoFilter ref="A3:'
        + _column_name(max(1, len(headers)))
        + f'{len(all_rows)}"/></worksheet>'
    )


def _cell(column: str, row: int, value: CellValue, *, header: bool) -> str:
    reference = f"{column}{row}"
    if value is None:
        return f'<c r="{reference}"/>'
    if isinstance(value, bool):
        return f'<c r="{reference}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (Decimal, int)):
        exponent = value.as_tuple().exponent if isinstance(value, Decimal) else 0
        style = 3 if isinstance(exponent, int) and exponent < -2 else 2
        return f'<c r="{reference}" s="{style}"><v>{escape(format(value, "f"))}</v></c>'
    cell_style = ' s="1"' if header else ""
    return f'<c r="{reference}" t="inlineStr"{cell_style}><is><t>{escape(value)}</t></is></c>'


def _column_name(index: int) -> str:
    result = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result
