"""Cross-cutting API v1 contract tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import create_access_token

from tests.integration.conftest import IdentityContext
from vglpos.app import create_app
from vglpos.config import TestingConfig
from vglpos.extensions import cache


def _limited_token(app: Flask, context: IdentityContext) -> str:
    with app.app_context():
        claims = {
            "company_id": context.company.id,
            "branch_id": context.branch.id,
            "terminal_id": context.terminal.id,
            "permissions": [],
            "roles": ["LIMITED"],
            "max_discount_percent": str(Decimal("0.00")),
            "idle_timeout": 1800,
            "sid": str(uuid4()),
        }
        token = create_access_token(identity=str(context.user.id), additional_claims=claims)
        from flask_jwt_extended import decode_token

        cache.set(f"jwt-session:{decode_token(token)['jti']}", "active", timeout=1800)
        return token


def test_openapi_covers_every_route(api_app: Flask, api_client: FlaskClient) -> None:
    response = api_client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.get_json()["paths"]
    missing: list[str] = []
    for rule in api_app.url_map.iter_rules():
        if not rule.rule.startswith("/api/v1/"):
            continue
        path = rule.rule.replace("<int:", "{").replace("<string:", "{").replace(">", "}")
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}:
            if method.lower() not in paths.get(path, {}):
                missing.append(f"{method} {path}")
    assert not missing
    assert response.get_json()["openapi"] == "3.1.0"
    assert paths["/api/v1/auth/login"]["post"]["security"] == []
    assert paths["/api/v1/auth/refresh"]["post"]["security"] == [{"bearerAuth": []}]
    assert "201" in paths["/api/v1/sales/checkout"]["post"]["responses"]
    checkout_parameters = paths["/api/v1/sales/checkout"]["post"]["parameters"]
    assert any(parameter["name"] == "Idempotency-Key" for parameter in checkout_parameters)
    product_parameters = paths["/api/v1/products"]["get"]["parameters"]
    assert {parameter["name"] for parameter in product_parameters} == {
        "barcode",
        "cursor",
        "limit",
        "q",
    }
    sale_parameter = paths["/api/v1/sales/{sale_id}"]["get"]["parameters"][0]
    assert sale_parameter == {
        "name": "sale_id",
        "in": "path",
        "required": True,
        "schema": {"type": "integer"},
    }


def test_swagger_ui_is_served_without_inline_script(api_client: FlaskClient) -> None:
    response = api_client.get("/api/v1/docs")
    assert response.status_code == 200
    assert b'<script src="/static/swagger-init.js"></script>' in response.data
    assert "unsafe-inline" not in response.headers["Content-Security-Policy"]


def test_openapi_documentation_requires_authentication_in_production() -> None:
    class DocsProductionConfig(TestingConfig):
        APP_ENV: str = "production"

    app = create_app(DocsProductionConfig)
    response = app.test_client().get("/api/v1/docs")
    assert response.status_code == 401


def test_every_mutating_route_is_idempotent(api_app: Flask) -> None:
    missing: list[str] = []
    for rule in api_app.url_map.iter_rules():
        methods = (rule.methods or set()) & {"POST", "PUT", "PATCH"}
        if (
            methods
            and getattr(api_app.view_functions[rule.endpoint], "_idempotent", False) is not True
        ):
            missing.append(f"{','.join(sorted(methods))} {rule.rule}")
    assert not missing


def test_protected_route_requires_token(api_client: FlaskClient) -> None:
    response = api_client.get("/api/v1/products")
    assert response.status_code == 401
    assert response.content_type == "application/problem+json"
    assert response.get_json()["request_id"]


def test_wrong_permission_is_forbidden(
    api_app: Flask, api_client: FlaskClient, api_identity: IdentityContext
) -> None:
    token = _limited_token(api_app, api_identity)
    response = api_client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_mutation_requires_idempotency_key(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    api_identity: IdentityContext,
) -> None:
    response = api_client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={"phone": "9000000001", "name": "Missing Key"},
    )
    assert response.status_code == 422

    malformed = api_client.post(
        "/api/v1/customers",
        headers={**auth_headers, "Idempotency-Key": "not-a-uuid"},
        json={"phone": "9000000001", "name": "Malformed Key"},
    )
    assert malformed.status_code == 422


def test_unknown_field_is_rejected(
    api_client: FlaskClient,
    mutation_headers: object,
) -> None:
    headers = mutation_headers()  # type: ignore[operator]
    response = api_client.post(
        "/api/v1/customers",
        headers=headers,
        json={"phone": "9000000002", "name": "Extra", "company_id": 999},
    )
    assert response.status_code == 422


def test_malformed_json_object_is_rejected(
    api_client: FlaskClient,
    mutation_headers: object,
) -> None:
    headers = mutation_headers()  # type: ignore[operator]
    response = api_client.post("/api/v1/customers", headers=headers, json=[])
    assert response.status_code == 422
