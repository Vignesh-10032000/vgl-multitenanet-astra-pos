"""Seed the disposable Phase 4 PostgreSQL performance dataset."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from itertools import islice
from typing import Any

from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from vglpos.domain.models import (
    Branch,
    Company,
    Customer,
    DocumentSeries,
    Permission,
    Product,
    Role,
    RolePermission,
    Sale,
    Shift,
    TaxRate,
    Terminal,
    User,
    UserRole,
)
from vglpos.security.password import hash_password
from vglpos.security.permissions import PERMISSION_DEFINITIONS

logger = logging.getLogger("vglpos.performance_seed")

PRODUCT_COUNT = 5_000
CUSTOMER_COUNT = 2_000
SALE_COUNT = 100_000
CHUNK_SIZE = 5_000


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for the performance seed.")
    return value


def _insert_chunks(session: Session, model: type[Any], rows: Iterable[dict[str, object]]) -> None:
    iterator = iter(rows)
    while chunk := list(islice(iterator, CHUNK_SIZE)):
        session.execute(insert(model), chunk)


def main() -> None:
    """Create one isolated tenant with the cardinalities required by Phase 4."""
    if os.environ.get("VGLPOS_ALLOW_PERFORMANCE_SEED") != "1":
        raise RuntimeError(
            "Set VGLPOS_ALLOW_PERFORMANCE_SEED=1 to acknowledge destructive seeding."
        )
    database_url = _required_env("DATABASE_URL")
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError("Performance seeding is restricted to databases ending in '_test'.")

    login_code = _required_env("PERF_LOGIN_CODE")
    username = _required_env("PERF_USERNAME")
    password = _required_env("PERF_PASSWORD")
    engine = create_engine(database_url, pool_pre_ping=True)
    with Session(engine) as session:
        if session.scalar(select(Company.id).where(Company.login_code == login_code)) is not None:
            raise RuntimeError(f"Performance company {login_code!r} already exists.")

        permissions = [
            Permission(
                code=definition.code,
                description=definition.description,
                category=definition.category,
            )
            for definition in PERMISSION_DEFINITIONS
        ]
        session.add_all(permissions)
        company = Company(
            name="VGL Performance Test",
            legal_name="VGL Performance Test Private Limited",
            login_code=login_code,
            state_code="33",
            address_line1="1 Benchmark Road",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600001",
            contact_email="performance@example.invalid",
            contact_phone="9000000000",
        )
        session.add(company)
        session.flush()
        branch = Branch(
            company_id=company.id,
            code="MAIN",
            name="Performance Branch",
            state_code="33",
            address_line1="1 Benchmark Road",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600001",
            phone="9000000001",
            is_head_office=True,
        )
        session.add(branch)
        session.flush()
        terminal = Terminal(
            company_id=company.id,
            branch_id=branch.id,
            code="LOAD-01",
            name="Load Test Counter",
        )
        user = User(
            company_id=company.id,
            username=username,
            email="cashier@example.invalid",
            password_hash=hash_password(password),
            full_name="Performance Cashier",
        )
        role = Role(
            company_id=company.id,
            name="OWNER",
            description="Performance test owner",
            is_system=True,
            max_discount_percent=Decimal("100.00"),
        )
        rate = TaxRate(
            company_id=company.id,
            name="GST 18% Performance",
            rate=Decimal("18.00"),
            cgst_rate=Decimal("9.00"),
            sgst_rate=Decimal("9.00"),
            igst_rate=Decimal("18.00"),
            cess_rate=Decimal("0.00"),
            effective_from=date(2017, 7, 1),
        )
        session.add_all([terminal, user, role, rate])
        session.flush()
        session.add(
            Shift(
                company_id=company.id,
                branch_id=branch.id,
                terminal_id=terminal.id,
                cashier_id=user.id,
                opening_cash=Decimal("0.00"),
                status="OPEN",
                opening_denominations={},
            )
        )
        session.add_all(
            RolePermission(
                company_id=company.id,
                role_id=role.id,
                permission_id=permission.id,
            )
            for permission in permissions
        )
        session.add(
            UserRole(
                company_id=company.id,
                user_id=user.id,
                role_id=role.id,
                branch_id=branch.id,
            )
        )
        session.add(
            DocumentSeries(
                company_id=company.id,
                branch_id=branch.id,
                doc_type="SALE",
                prefix="P/",
                current_number=SALE_COUNT,
                financial_year="26-27",
            )
        )
        session.flush()

        _insert_chunks(
            session,
            Product,
            (
                {
                    "company_id": company.id,
                    "sku": f"PERF-SKU-{index:05d}",
                    "name": f"Benchmark Product {index:05d}",
                    "tax_rate_id": rate.id,
                    "barcode": f"PERF-{index:05d}",
                    "cost_price": Decimal("50.00"),
                    "selling_price": Decimal("100.00"),
                    "mrp": Decimal("118.00"),
                    "on_hand": Decimal("1000000.000"),
                    "created_by": user.id,
                }
                for index in range(1, PRODUCT_COUNT + 1)
            ),
        )
        customer_ids = list(
            session.scalars(
                insert(Customer).returning(Customer.id),
                [
                    {
                        "company_id": company.id,
                        "phone": f"8{index:09d}",
                        "name": f"Benchmark Customer {index:04d}",
                        "state_code": "33",
                        "total_spent": Decimal("5000.00"),
                        "total_orders": 50,
                        "created_by": user.id,
                    }
                    for index in range(1, CUSTOMER_COUNT + 1)
                ],
            )
        )
        today = date.today()
        _insert_chunks(
            session,
            Sale,
            (
                {
                    "company_id": company.id,
                    "branch_id": branch.id,
                    "terminal_id": terminal.id,
                    "customer_id": customer_ids[index % CUSTOMER_COUNT],
                    "cashier_id": user.id,
                    "invoice_number": f"PERF/{index + 1:09d}",
                    "business_date": today - timedelta(days=index % 365),
                    "sale_status": "COMPLETED",
                    "supply_type": "INTRASTATE",
                    "gross_amount": Decimal("100.00"),
                    "discount_amount": Decimal("0.00"),
                    "taxable_amount": Decimal("100.00"),
                    "cgst_amount": Decimal("0.00"),
                    "sgst_amount": Decimal("0.00"),
                    "igst_amount": Decimal("0.00"),
                    "cess_amount": Decimal("0.00"),
                    "round_off": Decimal("0.00"),
                    "net_amount": Decimal("100.00"),
                    "amount_paid": Decimal("100.00"),
                    "balance_due": Decimal("0.00"),
                    "payment_method": "CASH",
                    "created_by": user.id,
                }
                for index in range(SALE_COUNT)
            ),
        )
        session.commit()

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("ANALYZE"))
        if engine.dialect.name == "postgresql":
            connection.execute(text("REFRESH MATERIALIZED VIEW mv_daily_sales_summary"))
    logger.info(
        "Performance seed complete: %s sales, %s products, %s customers; barcodes PERF-00001..",
        SALE_COUNT,
        PRODUCT_COUNT,
        CUSTOMER_COUNT,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
