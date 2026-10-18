"""Hard query ceilings for Phase 4 collection and fast-path endpoints."""

from __future__ import annotations

from collections.abc import Callable

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.orm import Session, raiseload

from tests.api.conftest import IdentityContext
from tests.performance.conftest import QueryBudget
from vglpos.api.v1.serializers import customer_response, product_response, sale_response
from vglpos.domain.models import Customer, Product, Sale
from vglpos.extensions import db


def test_sales_list_stays_within_four_queries(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    assert_max_queries: QueryBudget,
) -> None:
    with assert_max_queries(4):
        response = api_client.get("/api/v1/sales?limit=20", headers=auth_headers)
    assert response.status_code == 200


def test_customer_list_stays_within_two_queries(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    assert_max_queries: QueryBudget,
) -> None:
    with assert_max_queries(2):
        response = api_client.get("/api/v1/customers?limit=50", headers=auth_headers)
    assert response.status_code == 200


def test_revenue_year_stays_within_two_queries(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    assert_max_queries: QueryBudget,
) -> None:
    with assert_max_queries(2):
        response = api_client.get("/api/v1/reports/revenue?days=365", headers=auth_headers)
    assert response.status_code == 200


def test_weighted_inventory_valuation_is_one_set_query(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    assert_max_queries: QueryBudget,
) -> None:
    # One current-session check and one set query for the inventory data.
    with assert_max_queries(2) as statements:
        response = api_client.get(
            "/api/v1/reports/inventory-valuation?method=WEIGHTED_AVERAGE",
            headers=auth_headers,
        )
    assert response.status_code == 200
    assert len(statements) == 2
    assert sum("users.session_version" in statement for statement in statements) == 1
    assert sum("FROM products" in statement for statement in statements) == 1


def test_barcode_lookup_is_exactly_one_query(
    api_app: Flask,
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    api_identity: IdentityContext,
    assert_max_queries: QueryBudget,
) -> None:
    barcode = f"PERF-{api_identity.product.id}"
    with api_app.app_context(), Session(db.engine) as session:
        product = session.get(Product, api_identity.product.id)
        assert product is not None
        product.barcode = barcode
        session.commit()
    # One current-session check and one indexed product lookup.
    with assert_max_queries(2) as statements:
        response = api_client.get(
            f"/api/v1/products/lookup?barcode={barcode}",
            headers=auth_headers,
        )
    assert response.status_code == 200
    assert len(statements) == 2
    assert sum("users.session_version" in statement for statement in statements) == 1
    assert sum("FROM products" in statement for statement in statements) == 1


def test_collection_dto_serialization_never_lazy_loads(
    api_app: Flask,
    api_client: FlaskClient,
    mutation_headers: Callable[..., dict[str, str]],
    checkout_payload: dict[str, object],
    api_identity: IdentityContext,
    assert_max_queries: QueryBudget,
) -> None:
    customer = api_client.post(
        "/api/v1/customers",
        headers=mutation_headers(),
        json={"phone": "9000000999", "name": "No Lazy Loads"},
    )
    assert customer.status_code == 201
    sale = api_client.post(
        "/api/v1/sales/checkout",
        headers=mutation_headers(),
        json=checkout_payload,
    )
    assert sale.status_code == 201

    with api_app.app_context(), Session(db.engine) as session:
        product_model = session.scalar(
            select(Product).where(Product.id == api_identity.product.id).options(raiseload("*"))
        )
        customer_model = session.scalar(
            select(Customer).where(Customer.id == customer.get_json()["id"]).options(raiseload("*"))
        )
        sale_model = session.scalar(
            select(Sale).where(Sale.id == sale.get_json()["id"]).options(raiseload("*"))
        )
        assert product_model is not None
        assert customer_model is not None
        assert sale_model is not None
        with assert_max_queries(0):
            product_response(product_model)
            customer_response(customer_model)
            sale_response(sale_model)
