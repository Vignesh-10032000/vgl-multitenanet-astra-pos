"""Public demo workspace contracts."""

from __future__ import annotations

from uuid import uuid4

import pytest
from flask import Flask
from flask.testing import FlaskClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from vglpos.domain.models import Company, Customer, Product, Sale
from vglpos.extensions import cache, db
from vglpos.services.demo_service import DEMO_LOGIN_CODE


def _demo_login(client: FlaskClient) -> object:
    return client.post(
        "/api/v1/auth/demo-login",
        json={},
        headers={"Idempotency-Key": str(uuid4())},
    )


def test_demo_login_is_hidden_when_disabled(api_app: Flask, api_client: FlaskClient) -> None:
    api_app.config["DEMO_MODE_ENABLED"] = False
    assert _demo_login(api_client).status_code == 404


@pytest.mark.parametrize("dependency", ["database", "redis"])
def test_demo_dependency_outage_is_retryable_without_exposing_credentials(
    api_app: Flask,
    api_client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
    dependency: str,
) -> None:
    monkeypatch.setitem(api_app.config, "DEMO_MODE_ENABLED", True)

    def unavailable(*args: object, **kwargs: object) -> None:
        if dependency == "redis":
            raise RedisConnectionError("redis://private-password@internal")
        raise OperationalError("SELECT 1", {}, Exception("private-database-password"))

    if dependency == "redis":
        monkeypatch.setattr(cache, "get", unavailable)
    else:
        monkeypatch.setattr("vglpos.services.demo_service.DemoWorkspaceService.ensure", unavailable)

    response = _demo_login(api_client)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    assert body["type"] == "urn:vglpos:error:dependency-unavailable"
    assert body["request_id"] == response.headers["X-Request-Id"]
    assert "private-" not in response.get_data(as_text=True)


def test_demo_login_seeds_populated_isolated_workspace(
    api_app: Flask,
    api_client: FlaskClient,
    monkeypatch,
) -> None:
    monkeypatch.setitem(api_app.config, "DEMO_MODE_ENABLED", True)

    first = _demo_login(api_client)
    assert first.status_code == 200, first.get_data(as_text=True)
    body = first.get_json()
    assert body["user"]["full_name"] == "VGL Demo Explorer"
    assert body["user"]["branch_id"] is not None
    assert body["user"]["terminal_id"] is not None

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    for path in (
        "/api/v1/products?limit=50",
        "/api/v1/customers?limit=50",
        "/api/v1/sales?limit=50",
    ):
        response = api_client.get(path, headers=headers)
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["items"]

    with api_app.app_context(), Session(db.engine) as session:
        company_id = session.scalar(select(Company.id).where(Company.login_code == DEMO_LOGIN_CODE))
        assert company_id is not None
        assert (
            session.scalar(select(func.count(Product.id)).where(Product.company_id == company_id))
            == 8
        )
        assert (
            session.scalar(select(func.count(Customer.id)).where(Customer.company_id == company_id))
            == 5
        )
        assert (
            session.scalar(select(func.count(Sale.id)).where(Sale.company_id == company_id)) == 12
        )

    second = _demo_login(api_client)
    assert second.status_code == 200, second.get_data(as_text=True)

    with api_app.app_context(), Session(db.engine) as session:
        assert (
            session.scalar(
                select(func.count(Company.id)).where(Company.login_code == DEMO_LOGIN_CODE)
            )
            == 1
        )
