"""ROLE-01: Selecting an administrator portal never grants account privileges."""

from __future__ import annotations

from uuid import uuid4

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from tests.integration.conftest import IdentityContext
from vglpos.domain.models import Role
from vglpos.extensions import db


@pytest.mark.parametrize(
    ("account_role", "login_role", "status"),
    [
        ("CASHIER", "staff", 200),
        ("CASHIER", "admin", 403),
        ("CASHIER", "super_admin", 403),
        ("MANAGER", "admin", 403),
        ("ADMIN", "admin", 200),
        ("ADMIN", "super_admin", 403),
        ("ADMIN", "staff", 200),
        ("SUPER_ADMIN", "super_admin", 200),
        ("SUPER_ADMIN", "admin", 200),
        ("OWNER", "super_admin", 200),
        ("OWNER", "admin", 200),
    ],
)
def test_role_01_portal_checks_the_persisted_account_role_before_issuing_tokens(
    api_app: Flask,
    api_client: FlaskClient,
    api_identity: IdentityContext,
    login_payload: dict[str, object],
    account_role: str,
    login_role: str,
    status: int,
) -> None:
    with api_app.app_context(), Session(db.engine) as session:
        role = session.get(Role, api_identity.role.id)
        assert role is not None
        role.name = account_role
        session.commit()
    result = api_client.post(
        "/api/v1/auth/login",
        json={**login_payload, "login_role": login_role},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == status, result.get_data(as_text=True)
    body = result.get_json()
    if status == 200:
        assert body["user"]["roles"] == [account_role]
    else:
        assert "access_token" not in body
        assert "refresh_token" not in body


def test_role_02_unknown_portal_is_rejected(
    api_client: FlaskClient, login_payload: dict[str, object]
) -> None:
    result = api_client.post(
        "/api/v1/auth/login",
        json={**login_payload, "login_role": "root"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == 422


def test_role_03_wrong_password_does_not_disclose_portal_access(
    api_client: FlaskClient, login_payload: dict[str, object]
) -> None:
    result = api_client.post(
        "/api/v1/auth/login",
        json={**login_payload, "password": "wrong", "login_role": "super_admin"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == 401
    assert "assigned role" not in result.get_data(as_text=True)
