"""Product and customer endpoint behavior."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from flask import Flask
from flask.testing import FlaskClient
from PIL import Image

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


def test_localized_weighed_product_and_categories_are_exposed(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
    api_identity: IdentityContext,
) -> None:
    updated = api_client.put(
        f"/api/v1/products/{api_identity.product.id}",
        headers=mutation_headers(),
        json={
            "name_en": "Loose rice",
            "name_ta": "\u0b89\u0ba4\u0bbf\u0bb0\u0bbf \u0b85\u0bb0\u0bbf\u0b9a\u0bbf",
            "is_weighed": True,
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["name_en"] == "Loose rice"
    assert (
        updated.get_json()["name_ta"]
        == "\u0b89\u0ba4\u0bbf\u0bb0\u0bbf \u0b85\u0bb0\u0bbf\u0b9a\u0bbf"
    )
    assert updated.get_json()["is_weighed"] is True

    categories = api_client.get("/api/v1/products/categories", headers=auth_headers)
    assert categories.status_code == 200
    assert isinstance(categories.get_json()["items"], list)


def test_product_barcode_lookup_and_validation(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
    api_identity: IdentityContext,
) -> None:
    barcode = f"API-LOOKUP-{api_identity.product.id}"
    updated = api_client.put(
        f"/api/v1/products/{api_identity.product.id}",
        headers=mutation_headers(),
        json={"barcode": barcode},
    )
    assert updated.status_code == 200
    found = api_client.get(
        f"/api/v1/products/lookup?barcode={barcode}",
        headers=auth_headers,
    )
    assert found.status_code == 200
    assert found.get_json()["id"] == api_identity.product.id

    missing = api_client.get("/api/v1/products/lookup?barcode=unknown", headers=auth_headers)
    assert missing.status_code == 404
    invalid = api_client.get("/api/v1/products/lookup", headers=auth_headers)
    assert invalid.status_code == 422


def test_product_update_invalidates_cached_catalogue(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
    api_identity: IdentityContext,
) -> None:
    initial = api_client.get("/api/v1/products", headers=auth_headers)
    assert initial.status_code == 200
    assert initial.get_json()["items"][0]["name"] != "Updated Through Event"

    updated = api_client.put(
        f"/api/v1/products/{api_identity.product.id}",
        headers=mutation_headers(),
        json={"name": "Updated Through Event"},
    )
    assert updated.status_code == 200

    refreshed = api_client.get("/api/v1/products", headers=auth_headers)
    assert refreshed.status_code == 200
    assert refreshed.get_json()["items"][0]["name"] == "Updated Through Event"


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


def test_phase7_catalogue_operations_are_available_through_the_api(
    api_app: Flask,
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
    api_identity: IdentityContext,
    tmp_path: Path,
) -> None:
    api_app.config["PRODUCT_IMAGE_DIR"] = str(tmp_path / "product-images")
    csv_content = (
        "sku,name,tax_rate_id,cost_price,selling_price,mrp,barcode\n"
        f"IMPORT-API,Imported API product,{api_identity.product.tax_rate_id},10,20,25,IMPORT-001\n"
    ).encode()
    preview = api_client.post(
        "/api/v1/products/import/preview",
        headers=mutation_headers(),
        data={"file": (io.BytesIO(csv_content), "catalog.csv")},
        content_type="multipart/form-data",
    )
    assert preview.status_code == 200, preview.get_data(as_text=True)
    assert preview.get_json()["valid_rows"] == 1
    committed = api_client.post(
        "/api/v1/products/import/commit",
        headers=mutation_headers(),
        data={"file": (io.BytesIO(csv_content), "catalog.csv")},
        content_type="multipart/form-data",
    )
    assert committed.status_code == 201
    assert committed.get_json()["imported_count"] == 1

    invalid = b"sku,name,tax_rate_id,cost_price,selling_price,mrp\n,,999,x,-1,0\n"
    report = api_client.post(
        "/api/v1/products/import/error-report",
        headers=mutation_headers(),
        data={"file": (io.BytesIO(invalid), "errors.csv")},
        content_type="multipart/form-data",
    )
    assert report.status_code == 200
    assert report.headers["Content-Disposition"].endswith("product-import-errors.csv")
    assert b"sku is required" in report.data

    prices = api_client.post(
        "/api/v1/products/bulk-price-update",
        headers=mutation_headers(),
        json={
            "percentage": "5.00",
            "approver_user_id": api_identity.user.id,
            "approval_pin": api_identity.pin,
            "reason": "Approved API price review",
        },
    )
    assert prices.status_code == 200, prices.get_data(as_text=True)
    assert prices.get_json()["updated_count"] == 2

    labels = api_client.post(
        "/api/v1/products/barcode-labels",
        headers=mutation_headers(),
        json={"product_ids": [api_identity.product.id], "width_mm": "50", "height_mm": "30"},
    )
    assert labels.status_code == 200
    assert labels.content_type.startswith("image/svg+xml")
    assert b"<svg" in labels.data

    image_bytes = io.BytesIO()
    Image.new("RGB", (1200, 900), color=(12, 80, 110)).save(image_bytes, format="PNG")
    uploaded = api_client.post(
        f"/api/v1/products/{api_identity.product.id}/image",
        headers=mutation_headers(),
        data={"image": (io.BytesIO(image_bytes.getvalue()), "product.png")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_data(as_text=True)
    assert uploaded.get_json()["image_path"].endswith(".webp")
    stored = api_client.get(
        f"/api/v1/products/{api_identity.product.id}/image", headers=auth_headers
    )
    assert stored.status_code == 200
    assert stored.content_type == "image/webp"


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
