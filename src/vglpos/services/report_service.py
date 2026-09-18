"""Set-based operational and GST reporting queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from vglpos.domain.models import Customer, Sale, SaleItem, SalePayment
from vglpos.security.audit import record_audit_event
from vglpos.services.exceptions import ValidationError
from vglpos.utils.money import ZERO, money


@dataclass(frozen=True, slots=True)
class DailySummary:
    """Represent one company's reconciled daily sale totals."""

    total_bills: int
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    round_off: Decimal
    net_amount: Decimal


@dataclass(frozen=True, slots=True)
class RevenuePoint:
    """Represent one grouped date in a revenue series."""

    business_date: date
    total_bills: int
    net_amount: Decimal


@dataclass(frozen=True, slots=True)
class ProductSales:
    """Represent aggregate quantity and revenue for one product."""

    product_id: int
    quantity: Decimal
    revenue: Decimal


@dataclass(frozen=True, slots=True)
class PaymentMixEntry:
    """Represent aggregate tender use for one payment method."""

    payment_method: str
    transaction_count: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class Gstr1Row:
    """Represent a sale classified for one GSTR-1 outward-supply table."""

    table: str
    invoice_number: str
    business_date: date
    customer_gstin: str | None
    place_of_supply: str | None
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    invoice_value: Decimal


class ReportService:
    """Run tenant-scoped reports with one grouped query per requested report."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def daily_summary(self, on_date: date, *, branch_id: int | None = None) -> DailySummary:
        """Aggregate one day in a single query and never commit read-only work."""
        statement = select(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.gross_amount), ZERO),
            func.coalesce(func.sum(Sale.discount_amount), ZERO),
            func.coalesce(func.sum(Sale.taxable_amount), ZERO),
            func.coalesce(func.sum(Sale.cgst_amount), ZERO),
            func.coalesce(func.sum(Sale.sgst_amount), ZERO),
            func.coalesce(func.sum(Sale.igst_amount), ZERO),
            func.coalesce(func.sum(Sale.cess_amount), ZERO),
            func.coalesce(func.sum(Sale.round_off), ZERO),
            func.coalesce(func.sum(Sale.net_amount), ZERO),
        ).where(
            Sale.company_id == self.company_id,
            Sale.business_date == on_date,
            Sale.sale_status == "COMPLETED",
            Sale.deleted_at.is_(None),
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        row = self.session.execute(statement).one()
        return DailySummary(
            total_bills=int(row[0]),
            gross_amount=money(row[1]),
            discount_amount=money(row[2]),
            taxable_amount=money(row[3]),
            cgst_amount=money(row[4]),
            sgst_amount=money(row[5]),
            igst_amount=money(row[6]),
            cess_amount=money(row[7]),
            round_off=money(row[8]),
            net_amount=money(row[9]),
        )

    def revenue_series(
        self,
        start_date: date,
        end_date: date,
        *,
        branch_id: int | None = None,
    ) -> tuple[RevenuePoint, ...]:
        """Return all daily revenue points from one GROUP BY query."""
        if start_date > end_date:
            raise ValidationError("Revenue start date cannot be after end date.")
        statement = (
            select(Sale.business_date, func.count(Sale.id), func.sum(Sale.net_amount))
            .where(
                Sale.company_id == self.company_id,
                Sale.business_date.between(start_date, end_date),
                Sale.sale_status == "COMPLETED",
                Sale.deleted_at.is_(None),
            )
            .group_by(Sale.business_date)
            .order_by(Sale.business_date)
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        return tuple(
            RevenuePoint(business_date=row[0], total_bills=int(row[1]), net_amount=money(row[2]))
            for row in self.session.execute(statement)
        )

    def top_products(
        self,
        start_date: date,
        end_date: date,
        *,
        limit: int = 10,
        branch_id: int | None = None,
    ) -> tuple[ProductSales, ...]:
        """Rank products by stored line revenue using one grouped query."""
        self._validate_date_range(start_date, end_date)
        if limit < 1 or limit > 100:
            raise ValidationError("Top-products limit must be between 1 and 100.")
        statement = (
            select(
                SaleItem.product_id,
                func.sum(SaleItem.quantity),
                func.sum(SaleItem.total_amount),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                Sale.company_id == self.company_id,
                SaleItem.company_id == self.company_id,
                Sale.business_date.between(start_date, end_date),
                Sale.sale_status == "COMPLETED",
                Sale.deleted_at.is_(None),
                SaleItem.deleted_at.is_(None),
            )
            .group_by(SaleItem.product_id)
            .order_by(func.sum(SaleItem.total_amount).desc(), SaleItem.product_id)
            .limit(limit)
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        return tuple(
            ProductSales(product_id=row[0], quantity=row[1], revenue=money(row[2]))
            for row in self.session.execute(statement)
        )

    def payment_mix(
        self,
        start_date: date,
        end_date: date,
        *,
        branch_id: int | None = None,
    ) -> tuple[PaymentMixEntry, ...]:
        """Aggregate tender methods in one grouped query."""
        self._validate_date_range(start_date, end_date)
        statement = (
            select(
                SalePayment.payment_method,
                func.count(func.distinct(SalePayment.sale_id)),
                func.sum(SalePayment.amount),
            )
            .join(Sale, Sale.id == SalePayment.sale_id)
            .where(
                Sale.company_id == self.company_id,
                SalePayment.company_id == self.company_id,
                Sale.business_date.between(start_date, end_date),
                Sale.sale_status == "COMPLETED",
                Sale.deleted_at.is_(None),
                SalePayment.deleted_at.is_(None),
            )
            .group_by(SalePayment.payment_method)
            .order_by(SalePayment.payment_method)
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        return tuple(
            PaymentMixEntry(
                payment_method=row[0], transaction_count=int(row[1]), amount=money(row[2])
            )
            for row in self.session.execute(statement)
        )

    def gstr1_data(
        self,
        start_date: date,
        end_date: date,
        *,
        b2cl_threshold: Decimal = Decimal("100000.00"),
    ) -> tuple[Gstr1Row, ...]:
        """Classify B2B, B2C-large, and B2C-small invoices in one query."""
        self._validate_date_range(start_date, end_date)
        if b2cl_threshold <= ZERO:
            raise ValidationError("B2C-large threshold must be positive.")
        table_label = case(
            (Customer.gstin.is_not(None), "4A"),
            (
                (Sale.supply_type == "INTERSTATE") & (Sale.net_amount > b2cl_threshold),
                "5A",
            ),
            else_="7",
        )
        statement = (
            select(
                table_label,
                Sale.invoice_number,
                Sale.business_date,
                Customer.gstin,
                Customer.state_code,
                Sale.taxable_amount,
                Sale.cgst_amount,
                Sale.sgst_amount,
                Sale.igst_amount,
                Sale.cess_amount,
                Sale.net_amount,
            )
            .outerjoin(
                Customer,
                (Customer.id == Sale.customer_id)
                & (Customer.company_id == self.company_id)
                & Customer.deleted_at.is_(None),
            )
            .where(
                Sale.company_id == self.company_id,
                Sale.business_date.between(start_date, end_date),
                Sale.sale_status == "COMPLETED",
                Sale.deleted_at.is_(None),
            )
            .order_by(Sale.business_date, Sale.invoice_number)
        )
        return tuple(
            Gstr1Row(
                table=row[0],
                invoice_number=row[1],
                business_date=row[2],
                customer_gstin=row[3],
                place_of_supply=row[4],
                taxable_amount=money(row[5]),
                cgst_amount=money(row[6]),
                sgst_amount=money(row[7]),
                igst_amount=money(row[8]),
                cess_amount=money(row[9]),
                invoice_value=money(row[10]),
            )
            for row in self.session.execute(statement)
        )

    def record_export(
        self,
        *,
        user_id: int,
        report_name: str,
        start_date: date,
        end_date: date,
        output_format: str,
    ) -> None:
        """Commit an attributable audit event after an export is produced."""
        self._validate_date_range(start_date, end_date)
        normalized_name = report_name.strip()
        normalized_format = output_format.strip().upper()
        if not user_id or not normalized_name or not normalized_format:
            raise ValidationError("Export user, report name, and format are required.")
        record_audit_event(
            self.session,
            company_id=self.company_id,
            user_id=user_id,
            action="EXPORT",
            entity_type="Report",
            entity_id=normalized_name,
            new_values={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "format": normalized_format,
            },
        )
        self.session.commit()

    @staticmethod
    def _validate_date_range(start_date: date, end_date: date) -> None:
        if start_date > end_date:
            raise ValidationError("Report start date cannot be after end date.")
