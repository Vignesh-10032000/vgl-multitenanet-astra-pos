"""Hand-calculated 30-invoice GSTR-1 and statutory export regression gate."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import CreditNote, CreditNoteItem, Customer, Sale, SaleItem
from vglpos.services.report_export_service import ReportExportService, decimal_json_dumps
from vglpos.services.statutory_report_service import StatutoryReportService
from vglpos.utils.money import money

from .conftest import ServiceContext

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures"


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _seed_fixture(session: Session, context: ServiceContext, fixture: dict[str, object]) -> None:
    context.company.gstin = "33AAAAA0000A1Z5"
    context.product.name = "Hand-calculated commodity"
    customers = fixture["customers"]
    assert isinstance(customers, dict)
    customer_a_data = customers["A"]
    customer_b_data = customers["B"]
    assert isinstance(customer_a_data, dict) and isinstance(customer_b_data, dict)
    context.customer.name = str(customer_a_data["name"])
    context.customer.gstin = str(customer_a_data["gstin"])
    context.customer.state_code = str(customer_a_data["state_code"])
    customer_b = Customer(
        company_id=context.company.id,
        phone="7000000002",
        name=str(customer_b_data["name"]),
        gstin=str(customer_b_data["gstin"]),
        state_code=str(customer_b_data["state_code"]),
    )
    session.add(customer_b)
    session.flush()
    customer_map = {"A": context.customer, "B": customer_b}
    sales: dict[str, tuple[Sale, SaleItem]] = {}
    invoices = fixture["invoices"]
    assert isinstance(invoices, list) and len(invoices) == 30
    for raw in invoices:
        assert isinstance(raw, dict)
        taxable = _decimal(raw["taxable"])
        rate = _decimal(raw["rate"])
        tax = money(taxable * rate / Decimal("100"))
        intrastate = raw["supply"] == "INTRASTATE"
        cgst = money(tax / 2) if intrastate else Decimal("0.00")
        sgst = money(tax - cgst) if intrastate else Decimal("0.00")
        igst = Decimal("0.00") if intrastate else tax
        total = money(taxable + tax)
        customer_key = raw["customer"]
        customer = customer_map.get(str(customer_key)) if customer_key is not None else None
        sale = Sale(
            company_id=context.company.id,
            branch_id=context.branch.id,
            terminal_id=context.terminal.id,
            customer_id=customer.id if customer is not None else None,
            cashier_id=context.cashier.id,
            invoice_number=str(raw["number"]),
            business_date=date(2026, 8, 15),
            sale_status="COMPLETED",
            supply_type=str(raw["supply"]),
            place_of_supply=str(raw["pos"]),
            customer_gstin_at_sale=customer.gstin if customer is not None else None,
            customer_name_at_sale=customer.name if customer is not None else None,
            gross_amount=taxable,
            discount_amount=Decimal("0.00"),
            taxable_amount=taxable,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            cess_amount=Decimal("0.00"),
            round_off=Decimal("0.00"),
            net_amount=total,
            amount_paid=total,
            balance_due=Decimal("0.00"),
            payment_method="CASH",
        )
        session.add(sale)
        session.flush()
        item = SaleItem(
            company_id=context.company.id,
            sale_id=sale.id,
            product_id=context.product.id,
            line_number=1,
            quantity=Decimal("1.000"),
            unit_price=taxable,
            gross_amount=taxable,
            discount_amount=Decimal("0.00"),
            taxable_amount=taxable,
            tax_rate=rate,
            cgst_rate=money(rate / 2) if intrastate else Decimal("0.00"),
            sgst_rate=money(rate / 2) if intrastate else Decimal("0.00"),
            igst_rate=Decimal("0.00") if intrastate else rate,
            cess_rate=Decimal("0.00"),
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            cess_amount=Decimal("0.00"),
            cost_at_sale=Decimal("60.00"),
            hsn_code_at_sale="1001",
            uqc_at_sale="KGS",
            total_amount=total,
        )
        session.add(item)
        session.flush()
        sales[sale.invoice_number] = (sale, item)
    credit_notes = fixture["credit_notes"]
    assert isinstance(credit_notes, list)
    for raw in credit_notes:
        assert isinstance(raw, dict)
        sale, item = sales[str(raw["invoice"])]
        note = CreditNote(
            company_id=context.company.id,
            branch_id=context.branch.id,
            original_sale_id=sale.id,
            credit_note_number=str(raw["number"]),
            note_date=date.fromisoformat(str(raw["date"])),
            reason="CUSTOMER_REQUEST",
            net_amount=item.total_amount,
        )
        session.add(note)
        session.flush()
        session.add(
            CreditNoteItem(
                company_id=context.company.id,
                credit_note_id=note.id,
                original_sale_item_id=item.id,
                quantity=Decimal("1.000"),
                amount=item.total_amount,
            )
        )
    session.commit()


def test_hand_calculated_30_invoice_gstr1_matches_expected_json_exactly(
    service_session: Session,
    service_context: ServiceContext,
    tmp_path: Path,
) -> None:
    fixture = json.loads((FIXTURE_DIR / "gstr1_30_invoices.json").read_text(encoding="utf-8"))
    _seed_fixture(service_session, service_context, fixture)
    statutory = StatutoryReportService(service_session, service_context.company.id)
    report = statutory.gstr1(date(2026, 8, 1), date(2026, 8, 31))
    actual = ReportExportService(service_session, service_context.company.id).gstr1_json(report)
    expected_payload = json.loads(
        (FIXTURE_DIR / "gstr1_30_expected.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )
    expected = (decimal_json_dumps(expected_payload, indent=2) + "\n").encode("utf-8")
    if actual != expected:
        actual_path = tmp_path / "gstr1_actual.json"
        actual_path.write_bytes(actual)
        raise AssertionError(f"GSTR-1 JSON differs; actual artifact: {actual_path}")

    assert len(report.b2b) == 10
    assert len(report.b2cl) == 2
    assert len(report.cdnr) == 1
    assert statutory.reconciliation(date(2026, 8, 1), date(2026, 8, 31)) == ()
    gstr3b = statutory.gstr3b(date(2026, 8, 1), date(2026, 8, 31))
    assert gstr3b.outward_taxable.taxable_value == Decimal("202500.00")
    assert gstr3b.outward_taxable.igst_amount == Decimal("10080.00")
    assert gstr3b.outward_taxable.cgst_amount == Decimal("81.00")
    assert gstr3b.outward_taxable.sgst_amount == Decimal("81.00")
    assert gstr3b.outward_nil_exempt.taxable_value == Decimal("600.00")


def test_gstr1_offline_workbook_has_official_sections_and_tally_xml_is_well_formed(
    service_session: Session, service_context: ServiceContext, tmp_path: Path
) -> None:
    fixture = json.loads((FIXTURE_DIR / "gstr1_30_invoices.json").read_text(encoding="utf-8"))
    _seed_fixture(service_session, service_context, fixture)
    report = StatutoryReportService(service_session, service_context.company.id).gstr1(
        date(2026, 8, 1), date(2026, 8, 31)
    )
    exporter = ReportExportService(service_session, service_context.company.id)
    workbook_path = tmp_path / "gstr1.xlsx"
    workbook_path.write_bytes(exporter.gstr1_offline_xlsx(report))
    with ZipFile(workbook_path) as workbook:
        assert {name for name in workbook.namelist() if name.startswith("xl/worksheets/")} == {
            f"xl/worksheets/sheet{index}.xml" for index in range(1, 8)
        }
        workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
        assert all(
            name in workbook_xml
            for name in ("b2b,sez,de", "b2cl", "b2cs", "cdnr", "hsn(b2b)", "hsn(b2c)", "docs")
        )
    tally = exporter.tally_xml(date(2026, 8, 1), date(2026, 8, 31))
    assert tally.startswith(b"<?xml")
    assert tally.count(b'<TALLYMESSAGE xmlns:UDF="TallyUDF">') == 32


def test_reconciliation_flags_header_line_drift(
    service_session: Session, service_context: ServiceContext
) -> None:
    fixture = json.loads((FIXTURE_DIR / "gstr1_30_invoices.json").read_text(encoding="utf-8"))
    _seed_fixture(service_session, service_context, fixture)
    sale = service_session.scalar(select(Sale).where(Sale.invoice_number == "S/0002"))
    assert sale is not None
    sale.taxable_amount = Decimal("101.00")
    sale.net_amount = Decimal("119.00")
    service_session.commit()

    issues = StatutoryReportService(service_session, service_context.company.id).reconciliation(
        date(2026, 8, 1), date(2026, 8, 31)
    )

    assert {issue.issue for issue in issues} == {"HEADER_LINE_SUMS"}
