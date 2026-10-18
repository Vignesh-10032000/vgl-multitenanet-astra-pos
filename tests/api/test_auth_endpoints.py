"""Authentication endpoint contracts under mandatory mutation idempotency."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pyotp
from flask.testing import FlaskClient

from tests.integration.conftest import IdentityContext


def _key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def _login(client: FlaskClient, payload: dict[str, object]) -> dict[str, object]:
    response = client.post("/api/v1/auth/login", json=payload, headers=_key())
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_login_success_and_strict_failure(
    api_client: FlaskClient, login_payload: dict[str, object]
) -> None:
    body = _login(api_client, login_payload)
    assert body["access_token"]
    malformed = api_client.post(
        "/api/v1/auth/login",
        headers=_key(),
        json={**login_payload, "company_id": 999},
    )
    assert malformed.status_code == 422


def test_pin_login_success_and_failure(
    api_client: FlaskClient, api_identity: IdentityContext
) -> None:
    payload = {
        "company_code": api_identity.company.login_code,
        "user_id": api_identity.user.id,
        "pin": api_identity.pin,
        "branch_id": api_identity.branch.id,
        "terminal_id": api_identity.terminal.id,
    }
    assert (
        api_client.post("/api/v1/auth/pin-login", headers=_key(), json=payload).status_code == 200
    )
    assert (
        api_client.post(
            "/api/v1/auth/pin-login", headers=_key(), json={**payload, "pin": "0000"}
        ).status_code
        == 401
    )


def test_refresh_rotation_and_me(api_client: FlaskClient, login_payload: dict[str, object]) -> None:
    tokens = _login(api_client, login_payload)
    access_headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    profile = api_client.get("/api/v1/auth/me", headers=access_headers)
    assert profile.status_code == 200
    assert profile.get_json()["company_id"] == tokens["user"]["company_id"]
    assert api_client.get("/api/v1/auth/me").status_code == 401

    refresh_headers = {
        **_key(),
        "Authorization": f"Bearer {tokens['refresh_token']}",
    }
    refreshed = api_client.post("/api/v1/auth/refresh", headers=refresh_headers)
    assert refreshed.status_code == 200
    rejected = api_client.post(
        "/api/v1/auth/refresh",
        headers={**_key(), "Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert rejected.status_code == 401


def test_screen_lock_and_logout_revoke_access(
    api_client: FlaskClient, login_payload: dict[str, object]
) -> None:
    locked_tokens = _login(api_client, login_payload)
    locked_headers = {"Authorization": f"Bearer {locked_tokens['access_token']}"}
    locked = api_client.post("/api/v1/auth/screen-lock", headers={**locked_headers, **_key()})
    assert locked.status_code == 200
    assert api_client.get("/api/v1/auth/me", headers=locked_headers).status_code == 423

    logout_tokens = _login(api_client, login_payload)
    logout_headers = {"Authorization": f"Bearer {logout_tokens['access_token']}"}
    logout = api_client.post("/api/v1/auth/logout", headers={**logout_headers, **_key()})
    assert logout.status_code == 200
    assert api_client.get("/api/v1/auth/me", headers=logout_headers).status_code == 401


def test_mfa_setup_enable_disable_and_invalid_code(
    api_client: FlaskClient, login_payload: dict[str, object]
) -> None:
    tokens = _login(api_client, login_payload)
    auth = {"Authorization": f"Bearer {tokens['access_token']}"}
    setup = api_client.post(
        "/api/v1/auth/mfa/setup",
        headers={**auth, **_key()},
        json={"password": login_payload["password"]},
    )
    assert setup.status_code == 200
    uri = setup.get_json()["provisioning_uri"]
    secret = parse_qs(urlparse(uri).query)["secret"][0]

    invalid = api_client.post(
        "/api/v1/auth/mfa/enable",
        headers={**auth, **_key()},
        json={"code": "000000"},
    )
    assert invalid.status_code == 403
    assert api_client.get("/api/v1/auth/me", headers=auth).status_code == 200

    code = pyotp.TOTP(secret).now()
    enabled = api_client.post(
        "/api/v1/auth/mfa/enable", headers={**auth, **_key()}, json={"code": code}
    )
    assert enabled.status_code == 200
    disabled = api_client.post(
        "/api/v1/auth/mfa/disable", headers={**auth, **_key()}, json={"code": code}
    )
    assert disabled.status_code == 200
