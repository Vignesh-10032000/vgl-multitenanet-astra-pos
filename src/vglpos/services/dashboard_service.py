"""Current dashboard read model built from tenant-scoped operational data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vglpos.domain.models import Customer, Product, Sale, SaleItem, StockLedger
from vglpos.services.report_service import (
    DailySummary,
    PaymentMixEntry,
    ReportService,
    RevenuePoint,
)
from vglpos.utils.money import ZERO, money, qty


@dataclass(frozen=True, slots=True)
class DashboardProduct:
    product_id: int
    sku: str
    name: str
    name_en: str | None
    name_ta: str | None
    quantity: Decimal
    revenue: Decimal


@dataclass(frozen=True, slots=True)
class DashboardStock:
    product_id: int
    sku: str
    name: str
    name_en: str | None
    name_ta: str | None
    quantity: Decimal
    threshold: Decimal


@dataclass(frozen=True, slots=True)
class DashboardSale:
    id: int
    invoice_number: str
    customer_name: str | None
    item_quantity: Decimal
    created_at: datetime
    payment_method: str
    sale_status: str
    net_amount: Decimal


@dataclass(frozen=True, slots=True)
class DashboardOverview:
    on_date: date
    summary: DailySummary
    week_sales: Decimal
    month_sales: Decimal
    average_bill: Decimal
    total_products: int
    total_customers: int
    low_stock_count: int
    revenue: tuple[RevenuePoint, ...]
    top_products: tuple[DashboardProduct, ...]
    low_stock: tuple[DashboardStock, ...]
    payment_mix: tuple[PaymentMixEntry, ...]
    recent_sales: tuple[DashboardSale, ...]


class DashboardService:
    """Read the current dashboard without importing or activating the prototype."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def overview(self, on_date: date, *, branch_id: int | None = None) -> DashboardOverview:
        reports = ReportService(self.session, self.company_id)
        revenue = reports.revenue_series(on_date - timedelta(days=29), on_date, branch_id=branch_id)
        summary = self._daily_summary(on_date, branch_id)
        stock, stock_count = self._low_stock(branch_id)
        total_products = self.session.scalar(
            select(func.count(Product.id)).where(
                Product.company_id == self.company_id,
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
        )
        total_customers = self.session.scalar(
            select(func.count(Customer.id)).where(
                Customer.company_id == self.company_id,
                Customer.deleted_at.is_(None),
                Customer.is_active.is_(True),
            )
        )
        return DashboardOverview(
            on_date=on_date,
            summary=summary,
            week_sales=money(sum((point.net_amount for point in revenue[-7:]), ZERO)),
            month_sales=money(sum((point.net_amount for point in revenue), ZERO)),
            average_bill=money(summary.net_amount / summary.total_bills)
            if summary.total_bills
            else ZERO,
            total_products=int(total_products or 0),
            total_customers=int(total_customers or 0),
            low_stock_count=stock_count,
            revenue=revenue[-7:],
            top_products=self._top_products(on_date, branch_id),
            low_stock=stock,
            payment_mix=reports.payment_mix(on_date, on_date, branch_id=branch_id),
            recent_sales=self._recent_sales(on_date, branch_id),
        )

    def _daily_summary(self, on_date: date, branch_id: int | None) -> DailySummary:
        fields = (
            Sale.gross_amount,
            Sale.discount_amount,
            Sale.taxable_amount,
            Sale.cgst_amount,
            Sale.sgst_amount,
            Sale.igst_amount,
            Sale.cess_amount,
            Sale.round_off,
            Sale.net_amount,
        )
        statement = select(
            func.count(Sale.id), *(func.coalesce(func.sum(field), ZERO) for field in fields)
        ).where(
            Sale.company_id == self.company_id,
            Sale.business_date == on_date,
            Sale.sale_status == "COMPLETED",
            Sale.deleted_at.is_(None),
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        row = self.session.execute(statement).one()
        return DailySummary(int(row[0]), *(money(value) for value in row[1:]))

    def _top_products(self, on_date: date, branch_id: int | None) -> tuple[DashboardProduct, ...]:
        ranked = ReportService(self.session, self.company_id).top_products(
            on_date - timedelta(days=29), on_date, limit=5, branch_id=branch_id
        )
        if not ranked:
            return ()
        products = {
            product.id: product
            for product in self.session.scalars(
                select(Product).where(
                    Product.company_id == self.company_id,
                    Product.id.in_([row.product_id for row in ranked]),
                )
            )
        }
        return tuple(
            DashboardProduct(
                row.product_id,
                products[row.product_id].sku,
                products[row.product_id].name,
                products[row.product_id].name_en,
                products[row.product_id].name_ta,
                qty(row.quantity),
                row.revenue,
            )
            for row in ranked
            if row.product_id in products
        )

    def _low_stock(self, branch_id: int | None) -> tuple[tuple[DashboardStock, ...], int]:
        balances = select(
            StockLedger.product_id,
            func.sum(StockLedger.quantity).label("quantity"),
        ).where(StockLedger.company_id == self.company_id, StockLedger.deleted_at.is_(None))
        if branch_id is not None:
            balances = balances.where(StockLedger.branch_id == branch_id)
        stock = balances.group_by(StockLedger.product_id).subquery()
        quantity = (
            func.coalesce(stock.c.quantity, ZERO) if branch_id is not None else Product.on_hand
        )
        statement = (
            select(Product, quantity.label("quantity"))
            .outerjoin(stock, stock.c.product_id == Product.id)
            .where(
                Product.company_id == self.company_id,
                Product.is_active.is_(True),
                Product.is_inventory_tracked.is_(True),
                Product.deleted_at.is_(None),
                quantity <= Product.low_stock_threshold,
            )
        )
        count = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        rows = self.session.execute(statement.order_by(quantity, Product.id).limit(5))
        return tuple(
            DashboardStock(
                product.id,
                product.sku,
                product.name,
                product.name_en,
                product.name_ta,
                qty(balance),
                qty(product.low_stock_threshold),
            )
            for product, balance in rows
        ), count

    def _recent_sales(self, on_date: date, branch_id: int | None) -> tuple[DashboardSale, ...]:
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
                Sale.deleted_at.is_(None),
                Sale.business_date <= on_date,
            )
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        rows = self.session.execute(
            statement.order_by(Sale.created_at.desc(), Sale.id.desc()).limit(8)
        ).all()
        if not rows:
            return ()
        quantities = dict(
            self.session.execute(
                select(SaleItem.sale_id, func.sum(SaleItem.quantity))
                .where(
                    SaleItem.company_id == self.company_id,
                    SaleItem.sale_id.in_([sale.id for sale, _customer in rows]),
                    SaleItem.deleted_at.is_(None),
                )
                .group_by(SaleItem.sale_id)
            )
            .tuples()
            .all()
        )
        return tuple(
            DashboardSale(
                sale.id,
                sale.invoice_number,
                sale.customer_name_at_sale or customer,
                qty(quantities.get(sale.id, ZERO)),
                sale.created_at,
                sale.payment_method,
                sale.sale_status,
                money(sale.net_amount),
            )
            for sale, customer in rows
        )
