"""Current dashboard totals, scope, stock and validation contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from tests.integration.conftest import IdentityContext
from vglpos.domain.models import Branch, StockLedger
from vglpos.extensions import db


def test_dashboard_reconciles_seeded_demo_and_exposes_legacy_feature_details(
    api_app: Flask, api_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(api_app.config, "DEMO_MODE_ENABLED", True)
    login = api_client.post(
        "/api/v1/auth/demo-login", json={}, headers={"Idempotency-Key": str(uuid4())}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.get_json()['access_token']}"}
    response = api_client.get("/api/v1/reports/dashboard", headers=headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["on_date"] == date.today().isoformat()
    assert body["summary"]["total_bills"] == 4
    assert body["summary"]["net_amount"] == "1391.28"
    assert body["summary"]["cgst_amount"] == "66.14"
    assert body["summary"]["sgst_amount"] == "66.14"
    assert body["week_sales"] == "4354.85"
    assert body["month_sales"] == "4354.85"
    assert body["average_bill"] == "347.82"
    assert body["total_products"] == 8
    assert body["total_customers"] == 5
    assert body["low_stock_count"] == 3
    assert len(body["low_stock"]) == 3
    assert len(body["revenue"]) == 7
    assert len(body["top_products"]) == 5
    assert body["top_products"][0]["revenue"] == "976.50"
    assert len(body["recent_sales"]) == 8
    assert body["recent_sales"][0]["customer_name"] == "Ananya Raman"
    assert Decimal(body["recent_sales"][0]["item_quantity"]) == Decimal("1")
    assert {entry["payment_method"] for entry in body["payment_mix"]} == {"CASH", "UPI", "CARD"}
    assert sum(Decimal(entry["amount"]) for entry in body["payment_mix"]) == Decimal("1391.28")


def test_dashboard_does_not_leak_other_company_sales_or_catalogue(
    api_client: FlaskClient, auth_headers: dict[str, str]
) -> None:
    response = api_client.get("/api/v1/reports/dashboard", headers=auth_headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["summary"]["total_bills"] == 0
    assert body["summary"]["net_amount"] == "0.00"
    assert body["average_bill"] == "0.00"
    assert body["total_products"] == 1
    assert body["total_customers"] == 0
    assert body["top_products"] == []
    assert body["recent_sales"] == []
    assert body["payment_mix"] == []


def test_dashboard_stock_uses_branch_ledger_instead_of_company_on_hand(
    api_app: Flask,
    api_client: FlaskClient,
    api_identity: IdentityContext,
    auth_headers: dict[str, str],
) -> None:
    with api_app.app_context(), Session(db.engine) as session:
        other_branch = Branch(
            company_id=api_identity.company.id,
            code="OTHER",
            name="Other branch",
            state_code="33",
            address_line1="2 Test Road",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600001",
            phone="9000000099",
        )
        session.add(other_branch)
        session.flush()
        session.add(
            StockLedger(
                company_id=api_identity.company.id,
                branch_id=other_branch.id,
                product_id=api_identity.product.id,
                txn_type="ADJUSTMENT",
                reference_type="TEST",
                reference_id="OTHER-BRANCH-STOCK",
                quantity=Decimal("500.000"),
                balance_after=Decimal("500.000"),
                unit_cost=Decimal("50.00"),
                created_by=api_identity.user.id,
            )
        )
        session.add(
            StockLedger(
                company_id=api_identity.company.id,
                branch_id=api_identity.branch.id,
                product_id=api_identity.product.id,
                txn_type="ADJUSTMENT",
                reference_type="TEST",
                reference_id="DASHBOARD-STOCK",
                quantity=Decimal("2.000"),
                balance_after=Decimal("2.000"),
                unit_cost=Decimal("50.00"),
                created_by=api_identity.user.id,
            )
        )
        session.commit()
    response = api_client.get("/api/v1/reports/dashboard", headers=auth_headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["low_stock_count"] == 1
    assert Decimal(body["low_stock"][0]["quantity"]) == Decimal("2.000")


def test_dashboard_date_filter_and_tenant_override_validation(
    api_client: FlaskClient, auth_headers: dict[str, str]
) -> None:
    assert api_client.get("/api/v1/reports/dashboard").status_code == 401
    assert (
        api_client.get(
            "/api/v1/reports/dashboard?on_date=invalid", headers=auth_headers
        ).status_code
        == 422
    )
    assert (
        api_client.get(
            "/api/v1/reports/dashboard?company_id=999&branch_id=999", headers=auth_headers
        ).status_code
        == 422
    )
    response = api_client.get("/api/v1/reports/dashboard?on_date=2000-01-01", headers=auth_headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["on_date"] == "2000-01-01"
    assert body["week_sales"] == "0.00"
    assert body["recent_sales"] == []
    assert len(body["revenue"]) == 7
