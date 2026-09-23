"""Isolated migrated application fixtures for API v1 tests."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from tests.integration.conftest import IdentityContext, seed_identity_context
from vglpos.app import create_app
from vglpos.config import TestingConfig
from vglpos.domain.models import DocumentSeries, Product
from vglpos.extensions import db


@pytest.fixture(scope="session")
def api_app(tmp_path_factory: pytest.TempPathFactory) -> Flask:
    """Build one migrated file database for complete request-stack tests."""
    database = tmp_path_factory.mktemp("phase3") / "api_test.db"
    database_url = f"sqlite+pysqlite:///{database.as_posix()}"
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url

    class ApiTestingConfig(TestingConfig):
        DATABASE_URL: str = database_url

    return create_app(ApiTestingConfig)


@pytest.fixture()
def api_client(api_app: Flask) -> FlaskClient:
    return api_app.test_client()


@pytest.fixture()
def api_identity(api_app: Flask) -> IdentityContext:
    """Seed a stocked owner tenant with a fiscal sale number series."""
    context = seed_identity_context(api_app)
    with api_app.app_context(), Session(db.engine) as session:
        product = session.get(Product, context.product.id)
        assert product is not None
        product.on_hand = 100
        session.add(
            DocumentSeries(
                company_id=context.company.id,
                branch_id=context.branch.id,
                doc_type="SALE",
                prefix="S/",
                current_number=0,
                financial_year="26-27",
            )
        )
        session.commit()
    return context


@pytest.fixture()
def login_payload(api_identity: IdentityContext) -> dict[str, object]:
    return {
        "company_code": api_identity.company.login_code,
        "username": api_identity.user.username,
        "password": api_identity.password,
        "branch_id": api_identity.branch.id,
        "terminal_id": api_identity.terminal.id,
    }


@pytest.fixture()
def auth_headers(api_client: FlaskClient, login_payload: dict[str, object]) -> dict[str, str]:
    response = api_client.post(
        "/api/v1/auth/login",
        json=login_payload,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


@pytest.fixture()
def mutation_headers(auth_headers: dict[str, str]) -> Callable[..., dict[str, str]]:
    def build(*, key: str | None = None) -> dict[str, str]:
        return {**auth_headers, "Idempotency-Key": key or str(uuid4())}

    return build


@pytest.fixture()
def api_open_shift(
    api_client: FlaskClient,
    mutation_headers: Callable[..., dict[str, str]],
) -> dict[str, object]:
    response = api_client.post(
        "/api/v1/shifts/open",
        headers=mutation_headers(),
        json={"opening_cash": "100.00", "denomination_counts": {"100": 1}},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


@pytest.fixture()
def checkout_payload(
    api_identity: IdentityContext, api_open_shift: dict[str, object]
) -> dict[str, object]:
    return {
        "lines": [{"product_id": api_identity.product.id, "quantity": "1.000"}],
        "payments": [{"method": "CASH", "amount": "118.00"}],
        "customer_id": None,
        "business_date": "2026-09-19",
        "order_discount": "0.00",
        "apply_round_off": True,
    }


@pytest.fixture()
def fixture_dir() -> Path:
    return Path(__file__).parent
