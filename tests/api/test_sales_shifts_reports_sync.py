"""Sale, drawer, reporting, receipt, and offline synchronization endpoints."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import create_access_token, decode_token
from sqlalchemy.orm import Session

from tests.integration.conftest import IdentityContext
from vglpos.domain.models import StockLedger
from vglpos.extensions import cache, db
from vglpos.security.permissions import KNOWN_PERMISSION_CODES


def test_quote_checkout_list_detail_and_cancel(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
    checkout_payload: dict[str, object],
    api_identity: IdentityContext,
) -> None:
    invalid = api_client.post(
        "/api/v1/sales/quote",
        headers=mutation_headers(),
        json={
            **checkout_payload,
            "lines": [{"product_id": api_identity.product.id, "quantity": "0"}],
        },
    )
    assert invalid.status_code == 422

    quote_payload = {key: value for key, value in checkout_payload.items() if key != "payments"}
    quote = api_client.post("/api/v1/sales/quote", headers=mutation_headers(), json=quote_payload)
    assert quote.status_code == 200, quote.get_data(as_text=True)
    assert quote.get_json()["net_amount"] == "118.00"
    assert api_client.get("/api/v1/sales", headers=auth_headers).get_json()["items"] == []

    key = str(uuid4())
    checkout = api_client.post(
        "/api/v1/sales/checkout",
        headers=mutation_headers(key=key),
        json=checkout_payload,
    )
    replay = api_client.post(
        "/api/v1/sales/checkout",
        headers=mutation_headers(key=key),
        json=checkout_payload,
    )
    assert checkout.status_code == replay.status_code == 201
    assert checkout.data == replay.data
    sale_id = checkout.get_json()["id"]

    listing = api_client.get("/api/v1/sales?limit=1", headers=auth_headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.get_json()["items"]] == [sale_id]
    detail = api_client.get(f"/api/v1/sales/{sale_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.get_json()["items"][0]["quantity"] == "1.000"
    assert detail.get_json()["items"][0]["sku"] == api_identity.product.sku
    assert detail.get_json()["items"][0]["name"] == api_identity.product.name
    assert detail.get_json()["payments"][0]["amount"] == "118.00"

    no_customer = api_client.post(
        f"/api/v1/sales/{sale_id}/receipt/whatsapp",
        headers=mutation_headers(),
        json={},
    )
    assert no_customer.status_code == 400

    cancelled = api_client.post(
        f"/api/v1/sales/{sale_id}/cancel",
        headers=mutation_headers(),
        json={
            "reason": "Cashier correction",
            "approver_user_id": api_identity.user.id,
            "approval_pin": api_identity.pin,
        },
    )
    assert cancelled.status_code == 200, cancelled.get_data(as_text=True)
    assert cancelled.get_json()["sale_status"] == "CANCELLED"

    repeated = api_client.post(
        f"/api/v1/sales/{sale_id}/cancel",
        headers=mutation_headers(),
        json={
            "reason": "Again",
            "approver_user_id": api_identity.user.id,
            "approval_pin": api_identity.pin,
        },
    )
    assert repeated.status_code == 409


def test_payment_preview_is_server_authoritative_and_limits_split_rows(
    api_client: FlaskClient,
    mutation_headers: Callable[..., dict[str, str]],
    checkout_payload: dict[str, object],
) -> None:
    quote_payload = {key: value for key, value in checkout_payload.items() if key != "payments"}
    balance = api_client.post(
        "/api/v1/sales/payment-preview",
        headers=mutation_headers(),
        json={**quote_payload, "payments": [{"method": "CASH", "amount": "100.00"}]},
    )
    assert balance.status_code == 200
    assert balance.get_json()["net_amount"] == "118.00"
    assert balance.get_json()["amount_received"] == "100.00"
    assert balance.get_json()["balance_due"] == "18.00"
    assert balance.get_json()["change_due"] == "0.00"

    change = api_client.post(
        "/api/v1/sales/payment-preview",
        headers=mutation_headers(),
        json={**quote_payload, "payments": [{"method": "CASH", "amount": "200.00"}]},
    )
    assert change.status_code == 200
    assert change.get_json()["change_due"] == "82.00"

    too_many = api_client.post(
        "/api/v1/sales/payment-preview",
        headers=mutation_headers(),
        json={
            **quote_payload,
            "payments": [{"method": "CASH", "amount": "20.00"}] * 6,
        },
    )
    assert too_many.status_code == 422

    non_cash_change = api_client.post(
        "/api/v1/sales/payment-preview",
        headers=mutation_headers(),
        json={**quote_payload, "payments": [{"method": "UPI", "amount": "120.00"}]},
    )
    assert non_cash_change.status_code == 422


def test_whatsapp_receipt_is_queued_for_the_stored_customer(
    monkeypatch: pytest.MonkeyPatch,
    api_app: Flask,
    api_client: FlaskClient,
    mutation_headers: Callable[..., dict[str, str]],
    checkout_payload: dict[str, object],
) -> None:
    customer = api_client.post(
        "/api/v1/customers",
        headers=mutation_headers(),
        json={"phone": "9000000300", "name": "Receipt Customer"},
    )
    assert customer.status_code == 201
    payload = {**checkout_payload, "customer_id": customer.get_json()["id"]}
    sale = api_client.post("/api/v1/sales/checkout", headers=mutation_headers(), json=payload)
    assert sale.status_code == 201

    queued: dict[str, object] = {}

    def fake_apply_async(*, kwargs: dict[str, object]) -> SimpleNamespace:
        queued.update(kwargs)
        return SimpleNamespace(id="task-123")

    monkeypatch.setattr("vglpos.api.v1.sales.send_whatsapp_receipt.apply_async", fake_apply_async)
    api_app.config.update(
        WHATSAPP_WEBHOOK_URL="https://provider.invalid/receipt",
        WHATSAPP_API_TOKEN="test-token",
        PUBLIC_RECEIPT_BASE_URL="https://receipts.invalid/sales",
    )
    response = api_client.post(
        f"/api/v1/sales/{sale.get_json()['id']}/receipt/whatsapp",
        headers=mutation_headers(),
        json={},
    )
    assert response.status_code == 202
    assert response.get_json() == {"status": "queued", "task_id": "task-123"}
    assert queued["phone"] == "9000000300"


def test_sale_ids_are_hidden_from_other_branches(
    api_app: Flask,
    api_client: FlaskClient,
    mutation_headers: Callable[..., dict[str, str]],
    checkout_payload: dict[str, object],
    api_identity: IdentityContext,
) -> None:
    sale = api_client.post(
        "/api/v1/sales/checkout", headers=mutation_headers(), json=checkout_payload
    )
    assert sale.status_code == 201
    with api_app.app_context():
        token = create_access_token(
            identity=str(api_identity.user.id),
            additional_claims={
                "company_id": api_identity.company.id,
                "branch_id": api_identity.branch.id + 999999,
                "terminal_id": api_identity.terminal.id,
                "permissions": sorted(KNOWN_PERMISSION_CODES),
                "roles": ["OWNER"],
                "max_discount_percent": "100.00",
                "idle_timeout": 600,
                "sid": str(uuid4()),
            },
        )
        cache.set(f"jwt-session:{decode_token(token)['jti']}", "active", timeout=600)
    hidden = api_client.get(
        f"/api/v1/sales/{sale.get_json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hidden.status_code == 404


def test_sale_can_be_cancelled_after_product_soft_delete(
    api_client: FlaskClient,
    mutation_headers: Callable[..., dict[str, str]],
    checkout_payload: dict[str, object],
    api_identity: IdentityContext,
) -> None:
    sale = api_client.post(
        "/api/v1/sales/checkout", headers=mutation_headers(), json=checkout_payload
    )
    assert sale.status_code == 201
    auth = {"Authorization": mutation_headers()["Authorization"]}
    deleted = api_client.delete(f"/api/v1/products/{api_identity.product.id}", headers=auth)
    assert deleted.status_code == 200
    cancelled = api_client.post(
        f"/api/v1/sales/{sale.get_json()['id']}/cancel",
        headers=mutation_headers(),
        json={
            "reason": "Voided after catalogue retirement",
            "approver_user_id": api_identity.user.id,
            "approval_pin": api_identity.pin,
        },
    )
    assert cancelled.status_code == 200, cancelled.get_data(as_text=True)


def test_shift_open_movement_close_and_conflicts(
    api_client: FlaskClient,
    mutation_headers: Callable[..., dict[str, str]],
) -> None:
    opened = api_client.post(
        "/api/v1/shifts/open",
        headers=mutation_headers(),
        json={"opening_cash": "100.00"},
    )
    assert opened.status_code == 201
    shift_id = opened.get_json()["id"]

    conflict = api_client.post(
        "/api/v1/shifts/open",
        headers=mutation_headers(),
        json={"opening_cash": "50.00"},
    )
    assert conflict.status_code == 409

    movement = api_client.post(
        "/api/v1/shifts/cash-movement",
        headers=mutation_headers(),
        json={
            "shift_id": shift_id,
            "movement_type": "PAY_IN",
            "amount": "25.00",
            "reason": "Extra float",
        },
    )
    assert movement.status_code == 201
    assert movement.get_json()["amount"] == "25.00"

    invalid = api_client.post(
        "/api/v1/shifts/cash-movement",
        headers=mutation_headers(),
        json={
            "shift_id": shift_id,
            "movement_type": "PAY_OUT",
            "amount": "0.00",
            "reason": "Invalid",
        },
    )
    assert invalid.status_code == 422

    closed = api_client.post(
        "/api/v1/shifts/close",
        headers=mutation_headers(),
        json={"shift_id": shift_id, "counted_cash": "125.00"},
    )
    assert closed.status_code == 200
    assert closed.get_json()["status"] == "CLOSED"
    assert closed.get_json()["cash_difference"] == "0.00"

    already_closed = api_client.post(
        "/api/v1/shifts/close",
        headers=mutation_headers(),
        json={"shift_id": shift_id, "counted_cash": "125.00"},
    )
    assert already_closed.status_code == 409


def test_reports_success_and_validation_failures(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
) -> None:
    summary = api_client.get(
        "/api/v1/reports/daily-summary?on_date=2026-09-19", headers=auth_headers
    )
    assert summary.status_code == 200
    assert summary.get_json()["net_amount"] == "0.00"

    revenue = api_client.get("/api/v1/reports/revenue?days=7", headers=auth_headers)
    assert revenue.status_code == 200
    points = revenue.get_json()["items"]
    assert len(points) == 7
    assert revenue.get_json()["total_bills"] == 0
    assert revenue.get_json()["net_amount"] == "0.00"
    assert points[-1]["business_date"] == date.today().isoformat()
    assert all(point["net_amount"] == "0.00" for point in points)

    missing_date = api_client.get("/api/v1/reports/daily-summary", headers=auth_headers)
    assert missing_date.status_code == 422

    gstr1 = api_client.get(
        "/api/v1/reports/gstr1?start_date=2026-09-01&end_date=2026-09-30",
        headers=auth_headers,
    )
    assert gstr1.status_code == 200
    assert gstr1.get_json() == {"items": []}

    reversed_dates = api_client.get(
        "/api/v1/reports/gstr1?start_date=2026-10-01&end_date=2026-09-01",
        headers=auth_headers,
    )
    assert reversed_dates.status_code == 400

    valuation = api_client.get(
        "/api/v1/reports/inventory-valuation?method=WEIGHTED_AVERAGE",
        headers=auth_headers,
    )
    assert valuation.status_code == 200
    assert valuation.get_json()["method"] == "WEIGHTED_AVERAGE"

    invalid_method = api_client.get(
        "/api/v1/reports/inventory-valuation?method=LIFO", headers=auth_headers
    )
    assert invalid_method.status_code == 422


def test_inventory_valuation_uses_branch_ledger_quantity(
    api_app: Flask,
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    api_identity: IdentityContext,
) -> None:
    with api_app.app_context(), Session(db.engine) as session:
        session.add(
            StockLedger(
                company_id=api_identity.company.id,
                branch_id=api_identity.branch.id,
                product_id=api_identity.product.id,
                txn_type="ADJUSTMENT",
                reference_id="API-REPORT",
                reference_type="test",
                quantity=Decimal("5.000"),
                balance_after=Decimal("5.000"),
                unit_cost=Decimal("50.00"),
                created_by=api_identity.user.id,
            )
        )
        session.commit()
    response = api_client.get(
        "/api/v1/reports/inventory-valuation?method=WEIGHTED_AVERAGE",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.get_json()["items"][0]["quantity"] == "5.000"


def test_checkout_invalidates_cached_daily_summary(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
    checkout_payload: dict[str, object],
) -> None:
    endpoint = f"/api/v1/reports/daily-summary?on_date={date.today().isoformat()}"
    initial = api_client.get(endpoint, headers=auth_headers)
    assert initial.status_code == 200
    assert initial.get_json()["total_bills"] == 0

    checkout = api_client.post(
        "/api/v1/sales/checkout",
        headers=mutation_headers(),
        json={**checkout_payload, "business_date": date.today().isoformat()},
    )
    assert checkout.status_code == 201

    refreshed = api_client.get(endpoint, headers=auth_headers)
    assert refreshed.status_code == 200
    assert refreshed.get_json()["total_bills"] == 1


def test_offline_push_is_atomic_and_replay_safe(
    api_client: FlaskClient,
    mutation_headers: Callable[..., dict[str, str]],
    checkout_payload: dict[str, object],
) -> None:
    offline_uuid = str(uuid4())
    sale = {**checkout_payload, "offline_uuid": offline_uuid}
    response = api_client.post(
        "/api/v1/sync/offline-push",
        headers=mutation_headers(),
        json={"sales": [sale]},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    sale_id = response.get_json()["sales"][0]["id"]

    replay = api_client.post(
        "/api/v1/sync/offline-push",
        headers=mutation_headers(),
        json={"sales": [sale]},
    )
    assert replay.status_code == 201
    assert replay.get_json()["sales"][0]["id"] == sale_id

    duplicate = api_client.post(
        "/api/v1/sync/offline-push",
        headers=mutation_headers(),
        json={"sales": [sale, sale]},
    )
    assert duplicate.status_code == 400
