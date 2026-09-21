"""Request-stack coverage for Phase 6 catalogue and signed outbox APIs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.integration.conftest import IdentityContext
from vglpos.domain.models import Product, Sale
from vglpos.extensions import db


def _signed_sale(
    payload: dict[str, object], identifier: str, encoded_key: str
) -> dict[str, object]:
    sale = {
        **payload,
        "lines": [
            {**line, "line_discount": "0.00"}
            for line in payload["lines"]  # type: ignore[union-attr]
        ],
        "payments": [
            {**payment, "reference_number": None}
            for payment in payload["payments"]  # type: ignore[union-attr]
        ],
        "shift_id": None,
        "offline_uuid": identifier,
        "notes": None,
    }
    key = base64.urlsafe_b64decode(f"{encoded_key}=")
    canonical = json.dumps(sale, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    signature = (
        base64.urlsafe_b64encode(
            hmac.new(key, f"{identifier}.{canonical}".encode(), hashlib.sha256).digest()
        )
        .decode("ascii")
        .rstrip("=")
    )
    return {"uuid": identifier, "sale": sale, "signature": signature}


def test_signed_batch_api_replays_uuid_as_one_sale(
    api_app: Flask,
    api_client: FlaskClient,
    api_identity: IdentityContext,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
    checkout_payload: dict[str, object],
) -> None:
    bootstrap = api_client.get("/api/v1/sync/bootstrap", headers=auth_headers)
    assert bootstrap.status_code == 200
    facts = bootstrap.get_json()
    assert facts["terminal_code"] == api_identity.terminal.code
    assert facts["supplier_state"] == api_identity.branch.state_code
    assert facts["signing_algorithm"] == "HMAC-SHA-256"

    identifier = str(uuid4())
    operation = _signed_sale(checkout_payload, identifier, facts["signing_key"])
    first = api_client.post(
        "/api/v1/sync/batch",
        headers=mutation_headers(),
        json={"operations": [operation]},
    )
    replay = api_client.post(
        "/api/v1/sync/batch",
        headers=mutation_headers(),
        json={"operations": [operation]},
    )

    assert first.status_code == replay.status_code == 200
    assert first.get_json()["results"][0]["status"] == "synced"
    assert (
        first.get_json()["results"][0]["sale"]["id"]
        == replay.get_json()["results"][0]["sale"]["id"]
    )
    with api_app.app_context(), Session(db.engine) as session:
        count = session.scalar(
            select(func.count())
            .select_from(Sale)
            .where(
                Sale.company_id == api_identity.company.id,
                Sale.offline_uuid == identifier,
            )
        )
    assert count == 1


def test_batch_api_returns_permanent_signature_failure(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
    checkout_payload: dict[str, object],
) -> None:
    facts = api_client.get("/api/v1/sync/bootstrap", headers=auth_headers).get_json()
    identifier = str(uuid4())
    operation = _signed_sale(checkout_payload, identifier, facts["signing_key"])
    operation["signature"] = "A" * 43

    response = api_client.post(
        "/api/v1/sync/batch",
        headers=mutation_headers(),
        json={"operations": [operation]},
    )

    assert response.status_code == 200
    result = response.get_json()["results"][0]
    assert result["status"] == "failed"
    assert result["error_type"] == "invalid-offline-signature"


def test_catalog_api_returns_only_changed_tenant_rows(
    api_app: Flask,
    api_client: FlaskClient,
    api_identity: IdentityContext,
    auth_headers: dict[str, str],
) -> None:
    now = datetime.now(UTC)
    with api_app.app_context(), Session(db.engine) as session:
        changed = session.get(Product, api_identity.product.id)
        assert changed is not None
        changed.updated_at = now - timedelta(minutes=1)
        session.add(
            Product(
                company_id=api_identity.company.id,
                sku=f"OLD-{uuid4()}",
                name="Unchanged old product",
                tax_rate_id=changed.tax_rate_id,
                cost_price=Decimal("1.00"),
                selling_price=Decimal("2.00"),
                mrp=Decimal("2.00"),
                updated_at=now - timedelta(hours=2),
            )
        )
        session.commit()

    since = (now - timedelta(minutes=30)).isoformat()
    response = api_client.get(
        "/api/v1/products/catalog",
        query_string={"since": since},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["id"] for item in payload["items"]] == [api_identity.product.id]
    assert payload["items"][0]["tax_rate"] == "18.00"
    assert payload["truncated"] is False
