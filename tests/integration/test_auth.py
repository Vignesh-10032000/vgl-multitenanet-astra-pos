"""Phase 2 authentication integration tests."""

from __future__ import annotations

from time import perf_counter
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pyotp
from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import decode_token
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import AuditLog, User
from vglpos.extensions import db

from .conftest import IdentityContext


def _headers(**values: str) -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4()), **values}


def _login_payload(context: IdentityContext, *, password: str | None = None) -> dict[str, object]:
    return {
        "company_code": context.company.login_code,
        "username": context.user.username,
        "password": password if password is not None else context.password,
        "branch_id": context.branch.id,
        "terminal_id": context.terminal.id,
    }


def _login(client: FlaskClient, context: IdentityContext) -> dict[str, object]:
    response = client.post("/api/v1/auth/login", json=_login_payload(context), headers=_headers())
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert isinstance(body, dict)
    return body


def test_password_login_issues_tenant_scoped_claims(
    auth_app: Flask,
    auth_client: FlaskClient,
    identity_context: IdentityContext,
) -> None:
    body = _login(auth_client, identity_context)

    with auth_app.app_context():
        claims = decode_token(str(body["access_token"]))
    assert claims["sub"] == str(identity_context.user.id)
    assert claims["company_id"] == identity_context.company.id
    assert claims["branch_id"] == identity_context.branch.id
    assert claims["terminal_id"] == identity_context.terminal.id
    assert claims["idle_timeout"] == 600
    assert "user.manage" in claims["permissions"]
    assert claims["jti"]


def test_unknown_user_and_wrong_password_are_indistinguishable(
    auth_client: FlaskClient,
    identity_context: IdentityContext,
) -> None:
    wrong_payload = _login_payload(identity_context, password="definitely-wrong")
    started = perf_counter()
    wrong_response = auth_client.post("/api/v1/auth/login", json=wrong_payload, headers=_headers())
    wrong_duration = perf_counter() - started

    unknown_payload = {**wrong_payload, "username": "unknown-user"}
    started = perf_counter()
    unknown_response = auth_client.post(
        "/api/v1/auth/login", json=unknown_payload, headers=_headers()
    )
    unknown_duration = perf_counter() - started

    assert wrong_response.status_code == unknown_response.status_code == 401
    wrong_body = wrong_response.get_json()
    unknown_body = unknown_response.get_json()
    assert wrong_body["type"] == unknown_body["type"]
    assert wrong_body["title"] == unknown_body["title"]
    assert wrong_body["detail"] == unknown_body["detail"]
    assert abs(wrong_duration - unknown_duration) < 0.40


def test_lockout_after_five_failures(
    auth_app: Flask,
    auth_client: FlaskClient,
    identity_context: IdentityContext,
) -> None:
    for _ in range(5):
        response = auth_client.post(
            "/api/v1/auth/login",
            json=_login_payload(identity_context, password="wrong-password"),
            headers=_headers(),
        )
        assert response.status_code == 401

    with auth_app.app_context(), Session(db.engine) as session:
        user = session.get(User, identity_context.user.id)
        assert user is not None
        assert user.failed_login_attempts == 5
        assert user.locked_until is not None
        failures = list(
            session.scalars(
                select(AuditLog).where(
                    AuditLog.company_id == identity_context.company.id,
                    AuditLog.user_id == identity_context.user.id,
                    AuditLog.action == "LOGIN_FAILURE",
                )
            )
        )
        assert len(failures) == 5

    locked_response = auth_client.post(
        "/api/v1/auth/login", json=_login_payload(identity_context), headers=_headers()
    )
    assert locked_response.status_code == 401
    assert locked_response.get_json()["detail"] == "Invalid company code, username, or credential."


def test_refresh_token_rotation_invalidates_the_old_token(
    auth_client: FlaskClient,
    identity_context: IdentityContext,
) -> None:
    login_body = _login(auth_client, identity_context)
    original = str(login_body["refresh_token"])

    first = auth_client.post(
        "/api/v1/auth/refresh", headers=_headers(Authorization=f"Bearer {original}")
    )
    assert first.status_code == 200, first.get_data(as_text=True)
    replacement = str(first.get_json()["refresh_token"])
    assert replacement != original

    replay = auth_client.post(
        "/api/v1/auth/refresh", headers=_headers(Authorization=f"Bearer {original}")
    )
    assert replay.status_code == 401

    replacement_response = auth_client.post(
        "/api/v1/auth/refresh", headers=_headers(Authorization=f"Bearer {replacement}")
    )
    assert replacement_response.status_code == 200


def test_logout_revokes_access_and_its_refresh_token_family(
    auth_client: FlaskClient,
    identity_context: IdentityContext,
) -> None:
    login_body = _login(auth_client, identity_context)
    access_token = str(login_body["access_token"])
    refresh_token = str(login_body["refresh_token"])

    logout = auth_client.post(
        "/api/v1/auth/logout", headers=_headers(Authorization=f"Bearer {access_token}")
    )
    assert logout.status_code == 200
    assert (
        auth_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
        ).status_code
        == 401
    )
    assert (
        auth_client.post(
            "/api/v1/auth/refresh",
            headers=_headers(Authorization=f"Bearer {refresh_token}"),
        ).status_code
        == 401
    )


def test_screen_lock_requires_pin_and_keeps_identity_context(
    auth_client: FlaskClient,
    identity_context: IdentityContext,
) -> None:
    login_body = _login(auth_client, identity_context)
    access_token = str(login_body["access_token"])
    headers = {"Authorization": f"Bearer {access_token}"}

    lock_response = auth_client.post("/api/v1/auth/screen-lock", headers=_headers(**headers))
    assert lock_response.status_code == 200
    assert auth_client.get("/api/v1/auth/me", headers=headers).status_code == 423

    resume = auth_client.post(
        "/api/v1/auth/pin-login",
        json={
            "company_code": identity_context.company.login_code,
            "user_id": identity_context.user.id,
            "pin": identity_context.pin,
            "branch_id": identity_context.branch.id,
            "terminal_id": identity_context.terminal.id,
        },
        headers=_headers(),
    )
    assert resume.status_code == 200, resume.get_data(as_text=True)
    resumed_access = str(resume.get_json()["access_token"])
    resumed = auth_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {resumed_access}"}
    )
    assert resumed.status_code == 200
    assert resumed.get_json()["company_id"] == identity_context.company.id


def test_privileged_user_can_enable_and_require_totp_mfa(
    auth_client: FlaskClient,
    identity_context: IdentityContext,
) -> None:
    login_body = _login(auth_client, identity_context)
    headers = {"Authorization": f"Bearer {login_body['access_token']}"}

    setup = auth_client.post("/api/v1/auth/mfa/setup", headers=_headers(**headers))
    assert setup.status_code == 200
    provisioning_uri = setup.get_json()["provisioning_uri"]
    secret = parse_qs(urlparse(provisioning_uri).query)["secret"][0]
    code = pyotp.TOTP(secret).now()

    enabled = auth_client.post(
        "/api/v1/auth/mfa/enable", headers=_headers(**headers), json={"code": code}
    )
    assert enabled.status_code == 200
    missing_code = auth_client.post(
        "/api/v1/auth/login", json=_login_payload(identity_context), headers=_headers()
    )
    assert missing_code.status_code == 401

    payload = _login_payload(identity_context)
    payload["mfa_code"] = pyotp.TOTP(secret).now()
    authenticated = auth_client.post("/api/v1/auth/login", json=payload, headers=_headers())
    assert authenticated.status_code == 200
