"""Thin identity routes delegating all security decisions to Phase 2 services."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from flask import Blueprint, Response, current_app, g, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from sqlalchemy.orm import Session

from vglpos.api.v1.http import model_response, parse_body
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.auth import (
    AuthenticationResponse,
    LoginRequest,
    MfaCodeRequest,
    MfaSetupResponse,
    PinLoginRequest,
    UserProfileResponse,
)
from vglpos.api.v1.schemas.common import StatusResponse
from vglpos.extensions import db, limiter
from vglpos.security.auth_service import AuthenticationResult, AuthService, UserProfile
from vglpos.security.decorators import require_permission
from vglpos.security.tokens import TokenService
from vglpos.services.exceptions import AuthenticationError

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def _result_response(result: AuthenticationResult) -> tuple[Response, int]:
    return (
        jsonify(
            {
                "access_token": result.tokens.access_token,
                "refresh_token": result.tokens.refresh_token,
                "access_expires_in": result.tokens.access_expires_in,
                "refresh_expires_in": result.tokens.refresh_expires_in,
                "user": {
                    "id": result.user_id,
                    "company_id": result.company_id,
                    "branch_id": result.branch_id,
                    "terminal_id": result.terminal_id,
                    "full_name": result.full_name,
                    "roles": list(result.authorization.role_names),
                    "permissions": sorted(result.authorization.permissions),
                    "max_discount_percent": str(result.authorization.max_discount_percent),
                },
            }
        ),
        200,
    )


def _profile_response(profile: UserProfile) -> tuple[Response, int]:
    return model_response(
        UserProfileResponse(
            id=profile.user_id,
            company_id=profile.company_id,
            username=profile.username,
            email=profile.email,
            full_name=profile.full_name,
            branch_id=profile.branch_id,
            terminal_id=profile.terminal_id,
            roles=list(profile.role_names),
            permissions=sorted(profile.permissions),
            max_discount_percent=str(profile.max_discount_percent),
            mfa_enabled=profile.mfa_enabled,
        )
    )


def _refresh_required[**P, R](view: Callable[P, R]) -> Callable[P, R]:
    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        verify_jwt_in_request(refresh=True)
        claims = get_jwt()
        g.user_id = int(get_jwt_identity())
        g.company_id = int(claims["company_id"])
        return view(*args, **kwargs)

    return wrapped


def _login_username_rate_key() -> str:
    body = request.get_json(silent=True)
    company = str(body.get("company_code", "")) if isinstance(body, dict) else ""
    username = str(body.get("username", "")) if isinstance(body, dict) else ""
    return f"{company.upper()}:{username.lower()}"


def _remote_rate_key() -> str:
    return request.remote_addr or "unknown"


def _pin_rate_key() -> str:
    body = request.get_json(silent=True)
    company = str(body.get("company_code", "")) if isinstance(body, dict) else ""
    user_id = str(body.get("user_id", "")) if isinstance(body, dict) else ""
    return f"{request.remote_addr}:{company.upper()}:{user_id}"


@auth_bp.post("/login")
@limiter.limit("5 per 15 minutes", key_func=_remote_rate_key)
@limiter.limit("5 per 15 minutes", key_func=_login_username_rate_key)
@idempotent
@documented(
    summary="Authenticate with company code and password",
    request_model=LoginRequest,
    response_model=AuthenticationResponse,
    public=True,
)
def login() -> tuple[Response, int]:
    """Authenticate through an opaque company code without accepting tenant IDs."""
    command = parse_body(LoginRequest)
    with Session(db.engine) as session:
        result = AuthService(session).authenticate(
            command.company_code,
            command.username,
            command.password,
            branch_id=command.branch_id,
            terminal_id=command.terminal_id,
            mfa_code=command.mfa_code,
        )
    return _result_response(result)


@auth_bp.post("/pin-login")
@limiter.limit("3 per 15 minutes", key_func=_pin_rate_key)
@idempotent
@documented(
    summary="Resume a locked counter with a PIN",
    request_model=PinLoginRequest,
    response_model=AuthenticationResponse,
    public=True,
)
def pin_login() -> tuple[Response, int]:
    """Resume a locked counter through the more aggressively rate-limited PIN path."""
    command = parse_body(PinLoginRequest)
    with Session(db.engine) as session:
        result = AuthService(session).authenticate_pin(
            command.company_code,
            command.user_id,
            command.pin,
            branch_id=command.branch_id,
            terminal_id=command.terminal_id,
        )
    return _result_response(result)


@auth_bp.post("/refresh")
@_refresh_required
@idempotent
@documented(summary="Rotate a refresh token", response_model=AuthenticationResponse)
def refresh() -> tuple[Response, int]:
    """Rotate a refresh token and rebuild claims from current role assignments."""
    claims = get_jwt()
    if not TokenService().consume_refresh(claims):
        raise AuthenticationError("The session is no longer active.")
    with Session(db.engine) as session:
        result = AuthService(session).refresh(
            company_id=int(claims["company_id"]),
            user_id=int(get_jwt_identity()),
            branch_id=int(claims["branch_id"]) if claims.get("branch_id") is not None else None,
            terminal_id=(
                int(claims["terminal_id"]) if claims.get("terminal_id") is not None else None
            ),
        )
    return _result_response(result)


@auth_bp.post("/logout")
@require_permission()
@idempotent
@documented(summary="Revoke the active token family", response_model=StatusResponse)
def logout() -> tuple[Response, int]:
    """Revoke the presented token and retain a durable logout event."""
    claims = get_jwt()
    TokenService().revoke(claims)
    with Session(db.engine) as session:
        AuthService(session).record_logout(company_id=g.company_id, user_id=g.user_id)
    return jsonify({"status": "logged_out"}), 200


@auth_bp.get("/me")
@require_permission()
@documented(summary="Get the current user profile", response_model=UserProfileResponse)
def me() -> tuple[Response, int]:
    """Return a fresh tenant-scoped profile rather than trusting display claims."""
    with Session(db.engine) as session:
        profile = AuthService(session).profile(
            company_id=g.company_id,
            user_id=g.user_id,
            branch_id=g.branch_id,
            terminal_id=g.terminal_id,
        )
    return _profile_response(profile)


@auth_bp.post("/screen-lock")
@require_permission()
@idempotent
@documented(summary="Lock the active counter session", response_model=StatusResponse)
def screen_lock() -> tuple[Response, int]:
    """Revoke UI access without altering the active cash-drawer shift."""
    TokenService().lock_screen(get_jwt())
    return jsonify({"status": "locked", "resume_with": "pin-login"}), 200


@auth_bp.post("/mfa/setup")
@require_permission("user.manage")
@idempotent
@documented(summary="Create a TOTP provisioning secret", response_model=MfaSetupResponse)
def setup_mfa() -> tuple[Response, int]:
    """Return a provisioning URI only to privileged authenticated users."""
    with Session(db.engine) as session:
        uri = AuthService(session).setup_mfa(
            company_id=g.company_id,
            user_id=g.user_id,
            issuer_name=str(current_app.config["MFA_ISSUER_NAME"]),
        )
    return jsonify({"provisioning_uri": uri}), 200


@auth_bp.post("/mfa/enable")
@require_permission("user.manage")
@idempotent
@documented(
    summary="Enable TOTP MFA",
    request_model=MfaCodeRequest,
    response_model=StatusResponse,
)
def enable_mfa() -> tuple[Response, int]:
    """Activate a pending TOTP secret after one valid proof."""
    command = parse_body(MfaCodeRequest)
    with Session(db.engine) as session:
        AuthService(session).enable_mfa(
            company_id=g.company_id, user_id=g.user_id, code=command.code
        )
    return jsonify({"status": "enabled"}), 200


@auth_bp.post("/mfa/disable")
@require_permission("user.manage")
@idempotent
@documented(
    summary="Disable TOTP MFA",
    request_model=MfaCodeRequest,
    response_model=StatusResponse,
)
def disable_mfa() -> tuple[Response, int]:
    """Remove TOTP only after a current-code proof."""
    command = parse_body(MfaCodeRequest)
    with Session(db.engine) as session:
        AuthService(session).disable_mfa(
            company_id=g.company_id, user_id=g.user_id, code=command.code
        )
    return jsonify({"status": "disabled"}), 200
