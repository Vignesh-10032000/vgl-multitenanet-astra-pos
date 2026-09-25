"""Reference-data seed command integration tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from flask import Flask
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vglpos.app import create_app
from vglpos.config import TestingConfig
from vglpos.domain.models import Company, Permission, Role, RolePermission, TaxRate
from vglpos.domain.reference import STATE_CODES
from vglpos.extensions import db

EXPECTED_PERMISSION_CODES = {
    "sale.create",
    "sale.view",
    "sale.void",
    "sale.discount",
    "sale.price_override",
    "product.view",
    "product.create",
    "product.edit",
    "product.delete",
    "stock.adjust",
    "stock.view",
    "stock.audit",
    "stock.transfer",
    "stock.reorder",
    "customer.view",
    "customer.create",
    "customer.edit",
    "customer.export",
    "return.create",
    "return.approve",
    "report.view",
    "report.gst",
    "report.export",
    "shift.open",
    "shift.close",
    "cash.move",
    "user.manage",
    "settings.manage",
    "einvoice.generate",
    "einvoice.view",
    "einvoice.retry",
    "einvoice.cancel",
    "eway.generate",
    "purchase.create",
    "purchase.approve",
    "purchase.view",
    "purchase.receive",
    "purchase.invoice",
    "purchase.return",
    "supplier.view",
    "supplier.create",
    "supplier.pay",
}


def _company() -> Company:
    return Company(
        name="Test Company",
        legal_name="Test Company Private Limited",
        state_code="33",
        address_line1="Test Address",
        city="Chennai",
        state="Tamil Nadu",
        postal_code="600001",
        contact_email="test@example.invalid",
        contact_phone="0000000000",
    )


def _seed_app(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Flask:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    command.upgrade(Config("alembic.ini"), "head")
    return create_app(TestingConfig)


def test_seed_reference_is_complete_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'reference_seed_test.db').as_posix()}"
    app = _seed_app(database_url, monkeypatch)
    with app.app_context(), Session(db.engine) as session, session.begin():
        company = _company()
        session.add(company)
        session.flush()
        company_id = company.id

    runner = app.test_cli_runner()
    first = runner.invoke(args=["seed-reference", "--company-id", str(company_id)])
    assert first.exit_code == 0, first.output
    assert "37 state codes available" in first.output
    assert "42 permissions, 6 roles, and 9 GST rates inserted" in first.output

    second = runner.invoke(args=["seed-reference", "--company-id", str(company_id)])
    assert second.exit_code == 0, second.output
    assert "0 permissions, 0 roles, and 0 GST rates inserted" in second.output

    with app.app_context(), Session(db.engine) as session:
        assert len(STATE_CODES) == 37
        assert set(STATE_CODES) == {
            *(f"{code:02d}" for code in range(1, 25)),
            "26",
            "27",
            *(f"{code:02d}" for code in range(29, 39)),
            "97",
        }
        assert session.scalar(select(func.count()).select_from(Permission)) == 42
        assert session.scalar(select(func.count()).select_from(Role)) == 6
        assert session.scalar(select(func.count()).select_from(TaxRate)) == 9
        assert set(session.scalars(select(Permission.code))) == EXPECTED_PERMISSION_CODES
        role_permissions = {
            role.name: set(
                session.scalars(
                    select(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .where(RolePermission.role_id == role.id)
                )
            )
            for role in session.scalars(select(Role))
        }
        assert role_permissions["OWNER"] == EXPECTED_PERMISSION_CODES
        assert role_permissions["MANAGER"] == EXPECTED_PERMISSION_CODES - {
            "user.manage",
            "settings.manage",
        }
        assert role_permissions["CASHIER"] == {
            "sale.create",
            "sale.view",
            "product.view",
            "return.create",
            "shift.open",
            "shift.close",
            "cash.move",
            "customer.view",
            "customer.create",
        }
        assert role_permissions["ACCOUNTANT"] == {
            "sale.view",
            "customer.export",
            "report.view",
            "report.gst",
            "report.export",
            "purchase.view",
            "supplier.view",
            "supplier.pay",
            "einvoice.generate",
            "einvoice.view",
            "einvoice.retry",
            "einvoice.cancel",
            "eway.generate",
        }
        assert role_permissions["AUDITOR"].isdisjoint(
            {"sale.create", "product.create", "product.edit", "stock.adjust"}
        )
        schedules = {
            (rate.rate, rate.effective_from, rate.effective_to)
            for rate in session.scalars(select(TaxRate))
        }
    assert schedules == {
        *{
            (Decimal(slab), date(2017, 7, 1), date(2025, 9, 21))
            for slab in ("0", "5", "12", "18", "28")
        },
        *{(Decimal(slab), date(2025, 9, 22), None) for slab in ("0", "5", "18", "40")},
    }


def test_seed_reference_rejects_unknown_company(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'unknown_company_test.db').as_posix()}"
    app = _seed_app(database_url, monkeypatch)
    result = app.test_cli_runner().invoke(args=["seed-reference", "--company-id", "999999"])

    assert result.exit_code != 0
    assert "Company 999999 does not exist" in result.output
    with app.app_context(), Session(db.engine) as session:
        assert session.scalar(select(func.count()).select_from(Permission)) == 0
