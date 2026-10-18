"""Regression coverage for account grants, session revocation and safe logos."""

from __future__ import annotations

import base64
import io
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pyotp
import pytest
from flask import Flask
from flask.testing import FlaskClient
from PIL import Image
from sqlalchemy.orm import Session

from tests.integration.conftest import IdentityContext, seed_identity_context
from vglpos.extensions import db
from vglpos.services.store_profile_service import StoreProfileService


def _key(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid4())}


def test_pos_04_search_accepts_the_frontend_page_size_without_server_error(
    api_client: FlaskClient, auth_headers: dict[str, str]
) -> None:
    result = api_client.get("/api/v1/products?q=rice&limit=200", headers=auth_headers)
    assert result.status_code == 200, result.get_data(as_text=True)


def _member(password: str, role: str = "CASHIER") -> dict[str, object]:
    suffix = uuid4().hex[:8]
    return {
        "username": f"staff-{suffix}",
        "email": f"{suffix}@example.invalid",
        "full_name": "Checkout Staff",
        "role": role,
        "is_active": True,
        "password": "New staff password 42!",
        "pin": "753159",
        "actor_password": password,
    }


def _login(client: FlaskClient, identity: IdentityContext, member: dict[str, object]) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        headers=_key({}),
        json={
            "company_code": identity.company.login_code,
            "username": member["username"],
            "password": member["password"],
            "branch_id": identity.branch.id,
            "terminal_id": identity.terminal.id,
        },
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_sec_09_super_admin_signs_in_and_can_manage_company_admins(
    api_client: FlaskClient, api_identity: IdentityContext, auth_headers: dict[str, str]
) -> None:
    member = _member(api_identity.password, "SUPER_ADMIN")
    created = api_client.post("/api/v1/settings/team", headers=_key(auth_headers), json=member)
    assert created.status_code == 201
    tokens = _login(api_client, api_identity, member)
    assert tokens["user"]["roles"] == ["SUPER_ADMIN"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    created_admin = api_client.post(
        "/api/v1/settings/team",
        headers=_key(headers),
        json=_member(str(member["password"]), "ADMIN"),
    )
    assert created_admin.status_code == 201


def test_sec_01_cashier_role_is_enforced_on_api_and_refresh_is_revoked_on_disable(
    api_client: FlaskClient, api_identity: IdentityContext, auth_headers: dict[str, str]
) -> None:
    member = _member(api_identity.password)
    created = api_client.post("/api/v1/settings/team", headers=_key(auth_headers), json=member)
    assert created.status_code == 201, created.get_data(as_text=True)
    tokens = _login(api_client, api_identity, member)
    staff_headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert api_client.get("/api/v1/settings/team", headers=staff_headers).status_code == 403
    assert (
        api_client.put(
            "/api/v1/settings/store-logo", headers=_key(staff_headers), json={"image_base64": None}
        ).status_code
        == 403
    )
    assert (
        api_client.get("/api/v1/reports/revenue?days=7", headers=staff_headers).status_code == 403
    )
    changed = api_client.put(
        f"/api/v1/settings/team/{created.get_json()['id']}",
        headers=_key(auth_headers),
        json={**member, "is_active": False, "password": None},
    )
    assert changed.status_code == 200, changed.get_data(as_text=True)
    assert api_client.get("/api/v1/auth/me", headers=staff_headers).status_code == 401
    assert (
        api_client.post(
            "/api/v1/auth/refresh",
            headers=_key({"Authorization": f"Bearer {tokens['refresh_token']}"}),
        ).status_code
        == 401
    )


def test_sec_02_admin_cannot_grant_or_modify_admins_or_escalate_self(
    api_client: FlaskClient, api_identity: IdentityContext, auth_headers: dict[str, str]
) -> None:
    member = _member(api_identity.password, "ADMIN")
    response = api_client.post("/api/v1/settings/team", headers=_key(auth_headers), json=member)
    assert response.status_code == 201
    tokens = _login(api_client, api_identity, member)
    admin_headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    directory = api_client.get("/api/v1/settings/team", headers=admin_headers).get_json()
    assert "SUPER_ADMIN" not in directory["assignable_roles"]
    for role in ("SUPER_ADMIN", "ADMIN"):
        denied = api_client.post(
            "/api/v1/settings/team",
            headers=_key(admin_headers),
            json=_member(str(member["password"]), role),
        )
        assert denied.status_code == 403
    denied = api_client.put(
        f"/api/v1/settings/team/{api_identity.user.id}",
        headers=_key(admin_headers),
        json={**_member(str(member["password"])), "password": None},
    )
    assert denied.status_code == 403
    denied = api_client.put(
        f"/api/v1/settings/team/{response.get_json()['id']}",
        headers=_key(admin_headers),
        json={**member, "role": "CASHIER", "actor_password": member["password"]},
    )
    assert denied.status_code == 403
    created = api_client.post(
        "/api/v1/settings/team", headers=_key(admin_headers), json=_member(str(member["password"]))
    )
    assert created.status_code == 201


def test_sec_03_team_requires_password_and_keeps_tenants_isolated(
    api_app: Flask,
    api_client: FlaskClient,
    api_identity: IdentityContext,
    auth_headers: dict[str, str],
) -> None:
    member = _member("wrong password")
    assert (
        api_client.post(
            "/api/v1/settings/team", headers=_key(auth_headers), json=member
        ).status_code
        == 403
    )
    other = seed_identity_context(api_app)
    member["actor_password"] = api_identity.password
    assert (
        api_client.put(
            f"/api/v1/settings/team/{other.user.id}", headers=_key(auth_headers), json=member
        ).status_code
        == 404
    )
    directory = api_client.get("/api/v1/settings/team", headers=auth_headers).get_json()
    assert other.user.id not in {item["id"] for item in directory["members"]}
    assert (
        api_client.put(
            f"/api/v1/settings/team/{api_identity.user.id}", headers=_key(auth_headers), json=member
        ).status_code
        == 403
    )


def test_sec_04_logout_everywhere_revokes_access_and_refresh(
    api_client: FlaskClient,
    api_identity: IdentityContext,
    auth_headers: dict[str, str],
    login_payload: dict[str, object],
) -> None:
    another = api_client.post("/api/v1/auth/login", headers=_key({}), json=login_payload).get_json()
    response = api_client.post(
        "/api/v1/auth/logout-all",
        headers=_key(auth_headers),
        json={"password": api_identity.password},
    )
    assert response.status_code == 200
    assert api_client.get("/api/v1/auth/me", headers=auth_headers).status_code == 401
    assert (
        api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {another['access_token']}"}
        ).status_code
        == 401
    )
    assert (
        api_client.post(
            "/api/v1/auth/refresh",
            headers=_key({"Authorization": f"Bearer {another['refresh_token']}"}),
        ).status_code
        == 401
    )
    fresh = api_client.post("/api/v1/auth/login", headers=_key({}), json=login_payload)
    assert fresh.status_code == 200
    assert (
        api_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {fresh.get_json()['access_token']}"},
        ).status_code
        == 200
    )


def test_sec_05_enabled_mfa_cannot_be_reset_or_bypassed_with_pin(
    api_client: FlaskClient, api_identity: IdentityContext, auth_headers: dict[str, str]
) -> None:
    assert (
        api_client.post("/api/v1/auth/mfa/setup", headers=_key(auth_headers), json={}).status_code
        == 422
    )
    setup = api_client.post(
        "/api/v1/auth/mfa/setup",
        headers=_key(auth_headers),
        json={"password": api_identity.password},
    )
    secret = parse_qs(urlparse(setup.get_json()["provisioning_uri"]).query)["secret"][0]
    code = pyotp.TOTP(secret).now()
    assert (
        api_client.post(
            "/api/v1/auth/mfa/enable", headers=_key(auth_headers), json={"code": code}
        ).status_code
        == 200
    )
    assert (
        api_client.post(
            "/api/v1/auth/mfa/setup",
            headers=_key(auth_headers),
            json={"password": api_identity.password, "mfa_code": code},
        ).status_code
        == 400
    )
    assert api_client.get("/api/v1/auth/me", headers=auth_headers).get_json()["mfa_enabled"] is True
    response = api_client.post(
        "/api/v1/auth/pin-login",
        headers=_key({}),
        json={
            "company_code": api_identity.company.login_code,
            "user_id": api_identity.user.id,
            "pin": api_identity.pin,
        },
    )
    assert response.status_code == 401


def _image(size: tuple[int, int] = (24, 12)) -> str:
    output = io.BytesIO()
    image = Image.new("RGB", size, "blue")
    exif = image.getexif()
    exif[270] = "Private source-image metadata"
    image.save(output, "PNG", exif=exif)
    return base64.b64encode(output.getvalue()).decode("ascii")


def test_brand_01_logo_roundtrip_normalizes_and_removes_without_cross_tenant_leak(
    api_app: Flask,
    api_client: FlaskClient,
    api_identity: IdentityContext,
    auth_headers: dict[str, str],
) -> None:
    response = api_client.put(
        "/api/v1/settings/store-logo", headers=_key(auth_headers), json={"image_base64": _image()}
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    logo = response.get_json()["logo_data_uri"]
    assert logo.startswith("data:image/png;base64,")
    with Image.open(io.BytesIO(base64.b64decode(logo.split(",", 1)[1]))) as normalized:
        assert normalized.info == {}
    assert (
        api_client.get("/api/v1/settings/store-profile", headers=auth_headers).get_json()[
            "logo_data_uri"
        ]
        == logo
    )
    other = seed_identity_context(api_app)
    with api_app.app_context(), Session(db.engine) as session:
        assert (
            StoreProfileService(session, other.company.id, branch_id=other.branch.id)
            .get()
            .logo_data_uri
            is None
        )
    removed = api_client.put(
        "/api/v1/settings/store-logo", headers=_key(auth_headers), json={"image_base64": None}
    )
    assert removed.status_code == 200
    assert removed.get_json()["logo_data_uri"] is None


@pytest.mark.parametrize(
    "image",
    [
        "invalid-base64!",
        base64.b64encode(b'<svg onload="alert(1)"></svg>').decode(),
        _image((2049, 1)),
        base64.b64encode(b"x" * 512001).decode(),
    ],
    ids=["malformed", "svg", "oversize-dimensions", "oversize-file"],
)
def test_brand_02_unsafe_or_oversize_logo_is_rejected_without_mutating_profile(
    api_client: FlaskClient, auth_headers: dict[str, str], image: str
) -> None:
    before = api_client.get("/api/v1/settings/store-profile", headers=auth_headers).get_json()
    response = api_client.put(
        "/api/v1/settings/store-logo", headers=_key(auth_headers), json={"image_base64": image}
    )
    assert response.status_code in (400, 422)
    assert (
        api_client.get("/api/v1/settings/store-profile", headers=auth_headers).get_json() == before
    )
