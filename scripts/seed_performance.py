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
from vglpos.performance_workload import PRODUCT_COUNT, lane_for_index
from vglpos.security.password import hash_password
from vglpos.security.permissions import PERMISSION_DEFINITIONS
from vglpos.utils.gst import financial_year_code

logger = logging.getLogger("vglpos.performance_seed")

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
    cashier_count = int(os.environ.get("PERF_CASHIER_COUNT", "1"))
    first_branch_id = int(os.environ.get("PERF_BRANCH_ID", "1"))
    first_terminal_id = int(os.environ.get("PERF_TERMINAL_ID", "1"))
    lane_for_index(
        0,
        cashier_count,
        username=username,
        first_branch_id=first_branch_id,
        first_terminal_id=first_terminal_id,
    )
    engine = create_engine(database_url, pool_pre_ping=True)
    with Session(engine) as session:
        if session.scalar(select(Company.id).where(Company.login_code == login_code)) is not None:
            raise RuntimeError(f"Performance company {login_code!r} already exists.")
        if cashier_count > 1 and session.scalar(select(Branch.id).limit(1)) is not None:
            raise RuntimeError("Multi-cashier seeding requires a fresh test database.")

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
        session.add_all([role, rate])
        session.flush()
        session.add_all(
            RolePermission(
                company_id=company.id,
                role_id=role.id,
                permission_id=permission.id,
            )
            for permission in permissions
        )
        password_hash = hash_password(password)
        first_branch: Branch | None = None
        first_terminal: Terminal | None = None
        first_user: User | None = None
        for index in range(cashier_count):
            lane = lane_for_index(
                index,
                cashier_count,
                username=username,
                first_branch_id=first_branch_id,
                first_terminal_id=first_terminal_id,
            )
            branch = Branch(
                company_id=company.id,
                code="MAIN" if cashier_count == 1 else f"LOAD-{index + 1:03d}",
                name=f"Performance Branch {index + 1:03d}",
                state_code="33",
                address_line1="1 Benchmark Road",
                city="Chennai",
                state="Tamil Nadu",
                postal_code="600001",
                phone=f"9{index + 1:09d}",
                is_head_office=index == 0,
            )
            session.add(branch)
            session.flush()
            terminal = Terminal(
                company_id=company.id,
                branch_id=branch.id,
                code=f"LOAD-{index + 1:03d}",
                name=f"Load Test Counter {index + 1:03d}",
            )
            user = User(
                company_id=company.id,
                username=lane.username,
                email=f"cashier-{index + 1:03d}@example.invalid",
                password_hash=password_hash,
                full_name=f"Performance Cashier {index + 1:03d}",
            )
            session.add_all([terminal, user])
            session.flush()
            if branch.id != lane.branch_id or terminal.id != lane.terminal_id:
                raise RuntimeError(
                    "Performance lane IDs require a fresh, sequential test database."
                )
            session.add_all(
                [
                    Shift(
                        company_id=company.id,
                        branch_id=branch.id,
                        terminal_id=terminal.id,
                        cashier_id=user.id,
                        opening_cash=Decimal("0.00"),
                        status="OPEN",
                        opening_denominations={},
                    ),
                    UserRole(
                        company_id=company.id,
                        user_id=user.id,
                        role_id=role.id,
                        branch_id=branch.id,
                    ),
                    DocumentSeries(
                        company_id=company.id,
                        branch_id=branch.id,
                        doc_type="SALE",
                        prefix=f"P{index + 1:03d}/",
                        current_number=SALE_COUNT if index == 0 else 0,
                        financial_year=financial_year_code(date.today()),
                    ),
                ]
            )
            if index == 0:
                first_branch, first_terminal, first_user = branch, terminal, user
        session.flush()
        assert first_branch is not None and first_terminal is not None and first_user is not None
        branch, terminal, user = first_branch, first_terminal, first_user

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
        "Performance seed complete: %s sales, %s products, %s customers, %s cashiers",
        SALE_COUNT,
        PRODUCT_COUNT,
        CUSTOMER_COUNT,
        cashier_count,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
