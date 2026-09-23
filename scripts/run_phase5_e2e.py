"""Serve a disposable, migrated Phase 5 browser-test environment."""

from __future__ import annotations

import os
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from flask import Flask
from sqlalchemy.orm import Session

from vglpos.app import create_app
from vglpos.config import TestingConfig
from vglpos.domain.models import (
    Branch,
    Category,
    Company,
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
from vglpos.extensions import db
from vglpos.security.password import hash_password, hash_pin
from vglpos.security.permissions import PERMISSION_DEFINITIONS


def _seed(app: Flask) -> None:
    """Create one fully authorized browser identity and a scanner-ready catalogue."""
    with app.app_context(), Session(db.engine) as session:
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
            name="Phase 5 Browser Test",
            legal_name="Phase 5 Browser Test Private Limited",
            login_code="E2E",
            state_code="33",
            address_line1="1 Browser Test Road",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600001",
            contact_email="browser@example.invalid",
            contact_phone="9000000000",
        )
        session.add(company)
        session.flush()
        branch = Branch(
            company_id=company.id,
            code="MAIN",
            name="Browser Test Branch",
            state_code="33",
            address_line1="1 Browser Test Road",
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
            code="WEB-01",
            name="Browser Counter",
        )
        user = User(
            company_id=company.id,
            username="cashier",
            email="cashier@example.invalid",
            password_hash=hash_password("Browser-test-password-42!"),
            pin_hash=hash_pin("2468"),
            full_name="Browser Cashier",
        )
        role = Role(
            company_id=company.id,
            name="OWNER",
            description="Browser test owner",
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
        category = Category(
            company_id=company.id,
            name="Staples",
            name_en="Staples",
            name_ta="\u0bae\u0bb3\u0bbf\u0b95\u0bc8",
            code="STAPLES",
        )
        session.add_all([terminal, user, role, rate, category])
        session.flush()
        session.add(UserRole(company_id=company.id, user_id=user.id, role_id=role.id))
        session.add_all(
            RolePermission(
                company_id=company.id,
                role_id=role.id,
                permission_id=permission.id,
            )
            for permission in permissions
        )
        session.add_all(
            [
                Product(
                    company_id=company.id,
                    category_id=category.id,
                    sku="E2E-RICE-001",
                    barcode="8901234567890",
                    name="Rice bag",
                    name_en="Rice bag",
                    name_ta="\u0b85\u0bb0\u0bbf\u0b9a\u0bbf \u0baa\u0bc8",
                    tax_rate_id=rate.id,
                    cost_price=Decimal("75.00"),
                    selling_price=Decimal("100.00"),
                    mrp=Decimal("118.00"),
                    on_hand=Decimal("100.000"),
                ),
                Product(
                    company_id=company.id,
                    category_id=category.id,
                    sku="E2E-LOOSE-001",
                    barcode="8901234567891",
                    name="Loose rice",
                    name_en="Loose rice",
                    name_ta="\u0b89\u0ba4\u0bbf\u0bb0\u0bbf \u0b85\u0bb0\u0bbf\u0b9a\u0bbf",
                    tax_rate_id=rate.id,
                    cost_price=Decimal("40.00"),
                    selling_price=Decimal("60.00"),
                    mrp=Decimal("70.80"),
                    on_hand=Decimal("100.000"),
                    is_weighed=True,
                ),
            ]
        )
        session.add(
            DocumentSeries(
                company_id=company.id,
                branch_id=branch.id,
                doc_type="SALE",
                prefix="WEB/",
                current_number=0,
                financial_year="26-27",
            )
        )
        session.commit()


def main() -> None:
    """Migrate, seed, and run Flask until Playwright terminates the process."""
    port = int(os.environ.get("PHASE5_E2E_PORT", "5195"))
    with tempfile.TemporaryDirectory(prefix="vglpos-phase5-") as directory:
        database = Path(directory) / "phase5_e2e_test.db"
        database_url = f"sqlite+pysqlite:///{database.as_posix()}"
        os.environ["DATABASE_URL"] = database_url
        command.upgrade(Config("alembic.ini"), "head")

        class Phase5BrowserConfig(TestingConfig):
            DATABASE_URL: str = database_url

        app = create_app(Phase5BrowserConfig)
        _seed(app)
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
