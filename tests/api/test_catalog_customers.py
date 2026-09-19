"""Product and customer endpoint behavior."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from flask.testing import FlaskClient

from tests.integration.conftest import IdentityContext


def _product_payload(context: IdentityContext, suffix: str) -> dict[str, object]:
    return {
        "sku": f"API-{suffix}",
        "name": f"API Product {suffix}",
        "tax_rate_id": context.product.tax_rate_id,
        "cost_price": "10.00",
        "selling_price": "20.00",
        "mrp": "25.00",
    }


def test_product_catalogue_etag_and_decimal_strings(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    api_identity: IdentityContext,
) -> None:
    response = api_client.get("/api/v1/products", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["ETag"]
    item = response.get_json()["items"][0]
    assert item["id"] == api_identity.product.id
    assert item["selling_price"] == "100.00"
    assert isinstance(item["on_hand"], str)

    cached = api_client.get(
        "/api/v1/products",
        headers={**auth_headers, "If-None-Match": response.headers["ETag"]},
    )
    assert cached.status_code == 304
    assert cached.data == b""
    assert cached.headers["ETag"] == response.headers["ETag"]


def test_product_create_update_delete_and_failures(
    api_client: FlaskClient,
    mutation_headers: Callable[..., dict[str, str]],
    api_identity: IdentityContext,
) -> None:
    invalid = api_client.post(
        "/api/v1/products",
        headers=mutation_headers(),
        json={**_product_payload(api_identity, "BAD"), "mrp": "1.00"},
    )
    assert invalid.status_code == 400

    created = api_client.post(
        "/api/v1/products",
        headers=mutation_headers(),
        json=_product_payload(api_identity, "CRUD"),
    )
    assert created.status_code == 201, created.get_data(as_text=True)
    product_id = created.get_json()["id"]

    empty = api_client.put(f"/api/v1/products/{product_id}", headers=mutation_headers(), json={})
    assert empty.status_code == 422

    updated = api_client.put(
        f"/api/v1/products/{product_id}",
        headers=mutation_headers(),
        json={"selling_price": "21.00", "mrp": "25.00"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["selling_price"] == "21.00"
    assert updated.get_json()["row_version"] == 2

    deleted = api_client.delete(
        f"/api/v1/products/{product_id}",
        headers={"Authorization": mutation_headers()["Authorization"]},
    )
    assert deleted.status_code == 200
    assert deleted.get_json() == {"status": "deleted"}

    missing = api_client.delete(
        f"/api/v1/products/{product_id}",
        headers={"Authorization": mutation_headers()["Authorization"]},
    )
    assert missing.status_code == 404


def test_product_cursor_is_stable_across_insertions(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
    api_identity: IdentityContext,
) -> None:
    for suffix in ("PAGE-A", "PAGE-B"):
        response = api_client.post(
            "/api/v1/products",
            headers=mutation_headers(),
            json=_product_payload(api_identity, suffix),
        )
        assert response.status_code == 201

    first = api_client.get("/api/v1/products?limit=1", headers=auth_headers).get_json()
    assert first["next_cursor"]
    inserted = api_client.post(
        "/api/v1/products",
        headers=mutation_headers(),
        json=_product_payload(api_identity, "PAGE-NEW"),
    )
    assert inserted.status_code == 201
    second = api_client.get(
        f"/api/v1/products?limit=2&cursor={first['next_cursor']}", headers=auth_headers
    ).get_json()
    assert first["items"][0]["id"] not in {item["id"] for item in second["items"]}


def test_customer_idempotency_listing_and_detail(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
) -> None:
    key = str(uuid4())
    payload = {"phone": "9000000100", "name": "API Customer", "credit_limit": "500.00"}
    first = api_client.post("/api/v1/customers", headers=mutation_headers(key=key), json=payload)
    replay = api_client.post("/api/v1/customers", headers=mutation_headers(key=key), json=payload)
    assert first.status_code == replay.status_code == 201
    assert first.data == replay.data
    assert replay.headers["Idempotent-Replay"] == "true"
    customer_id = first.get_json()["id"]

    conflict = api_client.post(
        "/api/v1/customers",
        headers=mutation_headers(key=key),
        json={**payload, "name": "Changed"},
    )
    assert conflict.status_code == 409

    listing = api_client.get("/api/v1/customers?q=API", headers=auth_headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.get_json()["items"]] == [customer_id]

    detail = api_client.get(f"/api/v1/customers/{customer_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.get_json()["purchases"] == []

    missing = api_client.get("/api/v1/customers/99999999", headers=auth_headers)
    assert missing.status_code == 404


def test_customer_duplicate_phone_fails(
    api_client: FlaskClient,
    mutation_headers: Callable[..., dict[str, str]],
) -> None:
    payload = {"phone": "9000000200", "name": "First"}
    assert (
        api_client.post("/api/v1/customers", headers=mutation_headers(), json=payload).status_code
        == 201
    )
    duplicate = api_client.post(
        "/api/v1/customers", headers=mutation_headers(), json={**payload, "name": "Second"}
    )
    assert duplicate.status_code == 409
