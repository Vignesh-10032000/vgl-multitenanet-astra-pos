"""Phase 8 purchase and inventory HTTP contract smoke tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from flask.testing import FlaskClient

from vglpos.api.v1 import reports

from .conftest import IdentityContext


def _access_headers(client: FlaskClient, context: IdentityContext) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "company_code": context.company.login_code,
            "username": context.user.username,
            "password": context.password,
            "branch_id": context.branch.id,
            "terminal_id": context.terminal.id,
        },
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    return {"Authorization": f"Bearer {body['access_token']}"}


def test_supplier_and_variant_routes_use_phase8_schemas_and_permissions(
    auth_client: FlaskClient, identity_context: IdentityContext
) -> None:
    authorization = _access_headers(auth_client, identity_context)
    supplier_response = auth_client.post(
        "/api/v1/purchases/suppliers",
        headers={**authorization, "Idempotency-Key": str(uuid4())},
        json={
            "code": "API-SUP",
            "name": "API Supplier",
            "phone": "8000000077",
            "state_code": "33",
            "payment_terms_days": 30,
        },
    )
    assert supplier_response.status_code == 201, supplier_response.get_data(as_text=True)
    assert supplier_response.get_json()["outstanding_balance"] == "0.00"

    variant_response = auth_client.post(
        "/api/v1/inventory/variants",
        headers={**authorization, "Idempotency-Key": str(uuid4())},
        json={
            "parent_product_id": identity_context.product.id,
            "sku": f"{identity_context.product.sku}-BLUE-M",
            "name": "API Product Blue Medium",
            "selling_price": "105.00",
            "mrp": "118.00",
            "size": "M",
            "colour": "Blue",
            "style": "Regular",
        },
    )
    assert variant_response.status_code == 201, variant_response.get_data(as_text=True)
    variant = variant_response.get_json()
    assert variant["parent_product_id"] == identity_context.product.id
    assert variant["size"] == "M"
    assert variant["colour"] == "Blue"
    assert variant["tax_rate_id"] == identity_context.product.tax_rate_id

    near_expiry = auth_client.get(
        "/api/v1/inventory/near-expiry?on_date=2026-09-24",
        headers=authorization,
    )
    assert near_expiry.status_code == 200
    assert near_expiry.get_json() == {"items": []}


def test_report_job_route_queues_celery_and_exposes_status(
    auth_client: FlaskClient,
    identity_context: IdentityContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _access_headers(auth_client, identity_context)
    queued: list[dict[str, int]] = []

    def fake_delay(*, company_id: int, job_id: int) -> None:
        queued.append({"company_id": company_id, "job_id": job_id})

    monkeypatch.setattr(reports.generate_report_artifact, "delay", fake_delay)
    response = auth_client.post(
        "/api/v1/reports/jobs",
        headers={**authorization, "Idempotency-Key": str(uuid4())},
        json={
            "report_name": "GSTR3B",
            "output_format": "JSON",
            "parameters": {"start_date": "2026-09-01", "end_date": "2026-09-30"},
        },
    )

    assert response.status_code == 202, response.get_data(as_text=True)
    job = response.get_json()
    assert job["status"] == "PENDING"
    assert job["download_url"] is None
    assert queued == [{"company_id": identity_context.company.id, "job_id": job["id"]}]
    status = auth_client.get(f"/api/v1/reports/jobs/{job['id']}", headers=authorization)
    assert status.status_code == 200
    assert status.get_json()["status"] == "PENDING"
