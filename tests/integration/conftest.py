"""Phase 1D integration fixtures backed by disposable SQLite databases."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from flask import Flask, g, jsonify
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from vglpos.app import create_app
from vglpos.config import TestingConfig
from vglpos.domain.models import (
    Branch,
    Company,
    Customer,
    DocumentSeries,
    Permission,
    Product,
    Role,
    RolePermission,
    TaxRate,
    Terminal,
    User,
    UserRole,
)
from vglpos.extensions import Base, db
from vglpos.repositories.catalog import ProductRepository
from vglpos.security.decorators import require_permission
from vglpos.security.password import hash_password, hash_pin
from vglpos.security.permissions import PERMISSION_DEFINITIONS
from vglpos.services.exceptions import EntityNotFoundError


@dataclass(frozen=True, slots=True)
class ServiceContext:
    """Expose the persisted roots needed by service integration tests."""

    company: Company
    branch: Branch
    terminal: Terminal
    cashier: User
    tax_rate: TaxRate
    product: Product
    customer: Customer


@dataclass(frozen=True, slots=True)
class IdentityContext:
    """Expose one complete tenant identity for Phase 2 integration tests."""

    company: Company
    branch: Branch
    terminal: Terminal
    user: User
    role: Role
    product: Product
    password: str
    pin: str


@pytest.fixture(scope="module")
def auth_app(tmp_path_factory: pytest.TempPathFactory) -> Flask:
    """Build a migrated file-backed app for real request and token flows."""
    database = tmp_path_factory.mktemp("phase2") / "identity_test.db"
    database_url = f"sqlite+pysqlite:///{database.as_posix()}"
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url

    class Phase2TestingConfig(TestingConfig):
        DATABASE_URL: str = database_url

    app = create_app(Phase2TestingConfig)

    @require_permission("product.view")
    def _phase2_product_detail(product_id: int):  # type: ignore[no-untyped-def]
        with Session(db.engine) as session:
            product = ProductRepository(session, g.company_id).get(product_id)
            if product is None:
                raise EntityNotFoundError("Product was not found.")
            return jsonify({"id": product.id, "name": product.name})

    app.add_url_rule(
        "/api/v1/products/<int:product_id>",
        endpoint="phase2_product_detail",
        view_func=_phase2_product_detail,
    )
    return app


@pytest.fixture()
def auth_client(auth_app: Flask) -> FlaskClient:
    """Exercise Phase 2 through the complete Flask middleware stack."""
    return auth_app.test_client()


def seed_identity_context(auth_app: Flask) -> IdentityContext:
    """Seed an isolated owner identity with all permissions and one product."""
    suffix = uuid.uuid4().hex[:10]
    password = "Correct horse battery staple 42!"
    pin = "2468"
    with auth_app.app_context(), Session(db.engine, expire_on_commit=False) as session:
        permissions = {
            permission.code: permission for permission in session.scalars(select(Permission))
        }
        if not permissions:
            permission_rows = [
                Permission(
                    code=definition.code,
                    description=definition.description,
                    category=definition.category,
                )
                for definition in PERMISSION_DEFINITIONS
            ]
            session.add_all(permission_rows)
            session.flush()
            permissions = {permission.code: permission for permission in permission_rows}

        company = Company(
            name=f"Identity Test {suffix}",
            legal_name=f"Identity Test {suffix} Private Limited",
            login_code=f"TEST-{suffix}".upper(),
            state_code="33",
            address_line1="1 Security Street",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600001",
            contact_email=f"company-{suffix}@example.invalid",
            contact_phone=f"9{int(suffix, 16) % 1_000_000_000:09d}",
        )
        session.add(company)
        session.flush()
        branch = Branch(
            company_id=company.id,
            code="MAIN",
            name="Main Branch",
            state_code="33",
            address_line1="1 Security Street",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600001",
            phone=f"8{int(suffix, 16) % 1_000_000_000:09d}",
            is_head_office=True,
        )
        session.add(branch)
        session.flush()
        terminal = Terminal(
            company_id=company.id,
            branch_id=branch.id,
            code="T01",
            name="Counter 1",
        )
        user = User(
            company_id=company.id,
            username=f"owner-{suffix}",
            email=f"owner-{suffix}@example.invalid",
            password_hash=hash_password(password),
            pin_hash=hash_pin(pin),
            full_name="Test Owner",
        )
        role = Role(
            company_id=company.id,
            name="OWNER",
            description="Test owner",
            is_system=True,
            max_discount_percent=Decimal("100.00"),
        )
        rate = TaxRate(
            company_id=company.id,
            name="GST 18%",
            rate=Decimal("18.00"),
            cgst_rate=Decimal("9.00"),
            sgst_rate=Decimal("9.00"),
            igst_rate=Decimal("18.00"),
            cess_rate=Decimal("0.00"),
            effective_from=date(2017, 7, 1),
        )
        session.add_all([terminal, user, role, rate])
        session.flush()
        session.add(UserRole(company_id=company.id, user_id=user.id, role_id=role.id))
        session.add_all(
            RolePermission(
                company_id=company.id,
                role_id=role.id,
                permission_id=permission.id,
            )
            for permission in permissions.values()
        )
        product = Product(
            company_id=company.id,
            sku=f"SKU-{suffix}",
            name=f"Product {suffix}",
            tax_rate_id=rate.id,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
            mrp=Decimal("118.00"),
        )
        session.add(product)
        session.commit()
        return IdentityContext(
            company=company,
            branch=branch,
            terminal=terminal,
            user=user,
            role=role,
            product=product,
            password=password,
            pin=pin,
        )


@pytest.fixture()
def identity_factory(auth_app: Flask) -> Callable[[], IdentityContext]:
    """Create as many isolated tenants as one authorization test needs."""
    return lambda: seed_identity_context(auth_app)


@pytest.fixture()
def identity_context(auth_app: Flask) -> IdentityContext:
    """Seed one isolated tenant identity."""
    return seed_identity_context(auth_app)


@pytest.fixture()
def service_engine(tmp_path: Path) -> Engine:
    """Create a schema-complete disposable database for one test."""
    database = tmp_path / "phase1d_test.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE VIEW mv_daily_sales_summary AS
                SELECT company_id, branch_id, business_date,
                       COUNT(id) AS total_bills,
                       SUM(gross_amount) AS total_gross,
                       SUM(discount_amount) AS total_discount,
                       SUM(taxable_amount) AS total_taxable,
                       SUM(cgst_amount) AS total_cgst,
                       SUM(sgst_amount) AS total_sgst,
                       SUM(igst_amount) AS total_igst,
                       SUM(cess_amount) AS total_cess,
                       SUM(round_off) AS total_round_off,
                       SUM(net_amount) AS total_net
                FROM sales
                WHERE sale_status = 'COMPLETED' AND deleted_at IS NULL
                GROUP BY company_id, branch_id, business_date
                """
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def service_session(service_engine: Engine) -> Session:
    """Give each test a session whose committed work remains disposable."""
    with Session(service_engine, expire_on_commit=False) as session:
        yield session


def seed_service_context(
    session: Session,
    *,
    company_name: str = "Phase 1D Test Company",
    on_hand: Decimal = Decimal("1000.000"),
    tax_rate: Decimal = Decimal("18.00"),
    tax_inclusive: bool = False,
) -> ServiceContext:
    """Persist a minimal tenant, catalogue, and numbering configuration."""
    suffix = abs(hash(company_name)) % 1_000_000
    company = Company(
        name=company_name,
        legal_name=f"{company_name} Private Limited",
        state_code="33",
        address_line1="1 Test Street",
        city="Chennai",
        state="Tamil Nadu",
        postal_code="600001",
        contact_email=f"company-{suffix}@example.invalid",
        contact_phone=f"9{suffix:09d}",
    )
    session.add(company)
    session.flush()
    branch = Branch(
        company_id=company.id,
        code="MAIN",
        name="Main Branch",
        state_code="33",
        address_line1="1 Test Street",
        city="Chennai",
        state="Tamil Nadu",
        postal_code="600001",
        phone=f"8{suffix:09d}",
        is_head_office=True,
    )
    session.add(branch)
    session.flush()
    terminal = Terminal(
        company_id=company.id,
        branch_id=branch.id,
        code="T01",
        name="Counter 1",
    )
    cashier = User(
        company_id=company.id,
        username=f"cashier-{suffix}",
        email=f"cashier-{suffix}@example.invalid",
        password_hash="not-a-real-password-hash",
        full_name="Test Cashier",
    )
    rate = TaxRate(
        company_id=company.id,
        name=f"GST {tax_rate}",
        rate=tax_rate,
        cgst_rate=tax_rate / 2,
        sgst_rate=tax_rate / 2,
        igst_rate=tax_rate,
        cess_rate=Decimal("0.00"),
        effective_from=date(2017, 7, 1),
    )
    customer = Customer(
        company_id=company.id,
        phone=f"7{suffix:09d}",
        name="Test Customer",
        state_code="33",
    )
    session.add_all([terminal, cashier, rate, customer])
    session.flush()
    product = Product(
        company_id=company.id,
        sku="SKU-001",
        name="Test Product",
        tax_rate_id=rate.id,
        barcode=f"890{suffix:09d}",
        cost_price=Decimal("60.00"),
        selling_price=Decimal("100.00"),
        mrp=Decimal("118.00"),
        is_tax_inclusive=tax_inclusive,
        on_hand=on_hand,
    )
    session.add(product)
    session.flush()
    session.add_all(
        [
            DocumentSeries(
                company_id=company.id,
                branch_id=branch.id,
                doc_type="SALE",
                prefix="S/",
                current_number=0,
                financial_year="26-27",
            ),
            DocumentSeries(
                company_id=company.id,
                branch_id=branch.id,
                doc_type="CREDIT_NOTE",
                prefix="C/",
                current_number=0,
                financial_year="26-27",
            ),
        ]
    )
    session.commit()
    return ServiceContext(company, branch, terminal, cashier, rate, product, customer)


@pytest.fixture()
def service_context(service_session: Session) -> ServiceContext:
    """Provide one seeded tenant for a service integration test."""
    return seed_service_context(service_session)
