"""JWT issuance, rotation denylisting, and idle-session enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from flask import Flask, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from sqlalchemy.orm import Session

from vglpos.errors import problem_response
from vglpos.extensions import cache, db, jwt
from vglpos.repositories.identity import AuthorizationContext
from vglpos.services.session_security_service import SessionSecurityService

_DENYLIST_PREFIX = "jwt-denylist:"
_FAMILY_DENYLIST_PREFIX = "jwt-family-denylist:"
_SESSION_PREFIX = "jwt-session:"
_SCREEN_LOCK_PREFIX = "jwt-screen-lock:"


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int


class TokenService:
    """Keep JWT lifecycle state in Redis-backed cache rather than process memory."""

    def issue(
        self,
        *,
        user_id: int,
        company_id: int,
        branch_id: int | None,
        terminal_id: int | None,
        authorization: AuthorizationContext,
        session_version: int = 0,
    ) -> IssuedTokens:
        """Issue claims from verified persistence facts and activate idle tracking."""
        idle_timeout = 600 if "user.manage" in authorization.permissions else 1800
        session_family = str(uuid4())
        refresh_setting = current_app.config["JWT_REFRESH_TOKEN_EXPIRES"]
        refresh_seconds = (
            int(refresh_setting.total_seconds())
            if isinstance(refresh_setting, timedelta)
            else int(refresh_setting)
        )
        family_expires_at = int(datetime.now(UTC).timestamp()) + refresh_seconds
        claims = {
            "company_id": company_id,
            "session_version": session_version,
            "branch_id": branch_id,
            "terminal_id": terminal_id,
            "permissions": sorted(authorization.permissions),
            "roles": list(authorization.role_names),
            "max_discount_percent": str(authorization.max_discount_percent),
            "idle_timeout": idle_timeout,
            "sid": session_family,
            "family_exp": family_expires_at,
        }
        access_token = create_access_token(identity=str(user_id), additional_claims=claims)
        refresh_token = create_refresh_token(identity=str(user_id), additional_claims=claims)
        access_payload = decode_token(access_token)
        refresh_payload = decode_token(refresh_token)
        access_jti = str(access_payload["jti"])
        cache.set(f"{_SESSION_PREFIX}{access_jti}", "active", timeout=idle_timeout)
        return IssuedTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_in=int(access_payload["exp"]) - int(access_payload["iat"]),
            refresh_expires_in=int(refresh_payload["exp"]) - int(refresh_payload["iat"]),
        )

    def revoke(self, payload: dict[str, Any]) -> None:
        """Deny a token until its natural expiry so replay cannot restore it."""
        jti = str(payload.get("jti", ""))
        expires_at = int(payload.get("exp", 0))
        if not jti or expires_at <= 0:
            raise ValueError("JWT payload is missing revocation claims.")
        timeout = self._revocation_timeout(payload)
        cache.set(f"{_DENYLIST_PREFIX}{jti}", "revoked", timeout=timeout)
        self._revoke_family(payload, timeout=timeout)
        cache.delete(f"{_SESSION_PREFIX}{jti}")
        cache.delete(f"{_SCREEN_LOCK_PREFIX}{jti}")

    def consume_refresh(self, payload: dict[str, Any]) -> bool:
        """Atomically consume one refresh JTI before rotating its token family."""
        jti = str(payload.get("jti", ""))
        if payload.get("type") != "refresh" or not jti:
            raise ValueError("A refresh token payload is required.")
        timeout = self._revocation_timeout(payload)
        if not cache.add(f"{_DENYLIST_PREFIX}{jti}", "revoked", timeout=timeout):
            return False
        self._revoke_family(payload, timeout=timeout)
        return True

    @staticmethod
    def _revocation_timeout(payload: dict[str, Any]) -> int:
        expires_at = int(payload.get("exp", 0))
        if expires_at <= 0:
            raise ValueError("JWT payload is missing expiration claims.")
        family_expires_at = int(payload.get("family_exp", expires_at))
        return max(1, max(expires_at, family_expires_at) - int(datetime.now(UTC).timestamp()))

    @staticmethod
    def _revoke_family(payload: dict[str, Any], *, timeout: int) -> None:
        session_family = str(payload.get("sid", ""))
        if session_family:
            cache.set(f"{_FAMILY_DENYLIST_PREFIX}{session_family}", "revoked", timeout=timeout)

    def lock_screen(self, payload: dict[str, Any]) -> None:
        """Mark an access token locked while leaving the associated shift untouched."""
        jti = str(payload.get("jti", ""))
        expires_at = int(payload.get("exp", 0))
        if not jti or payload.get("type") != "access":
            raise ValueError("An access token is required for screen lock.")
        timeout = max(1, expires_at - int(datetime.now(UTC).timestamp()))
        cache.set(f"{_SCREEN_LOCK_PREFIX}{jti}", "locked", timeout=timeout)

    @staticmethod
    def is_screen_locked(payload: dict[str, Any]) -> bool:
        jti = str(payload.get("jti", ""))
        return bool(jti and cache.get(f"{_SCREEN_LOCK_PREFIX}{jti}") is not None)

    @staticmethod
    def is_blocked(payload: dict[str, Any]) -> bool:
        """Reject explicit revocations and access tokens whose idle state expired."""
        try:
            company_id = int(payload["company_id"])
            user_id = int(payload["sub"])
            version = int(payload.get("session_version", 0))
        except (KeyError, TypeError, ValueError):
            return True
        with Session(db.engine) as session:
            if not SessionSecurityService(session, company_id).is_current(user_id, version):
                return True
        jti = str(payload.get("jti", ""))
        session_family = str(payload.get("sid", ""))
        if (
            not jti
            or not session_family
            or cache.get(f"{_DENYLIST_PREFIX}{jti}") is not None
            or cache.get(f"{_FAMILY_DENYLIST_PREFIX}{session_family}") is not None
        ):
            return True
        if payload.get("type") != "access":
            return False
        session_key = f"{_SESSION_PREFIX}{jti}"
        if cache.get(session_key) is None:
            return True
        idle_timeout = int(payload.get("idle_timeout", 1800))
        cache.set(session_key, "active", timeout=idle_timeout)
        return False


def register_jwt_callbacks(app: Flask) -> None:
    """Make every JWT failure use the same RFC 7807 response surface."""

    @jwt.token_in_blocklist_loader
    def _token_in_blocklist(_header: dict[str, Any], payload: dict[str, Any]) -> bool:
        return TokenService.is_blocked(payload)

    @jwt.revoked_token_loader
    def _revoked(_header: dict[str, Any], _payload: dict[str, Any]) -> Any:
        return problem_response(
            status=401, title="Unauthorized", detail="The session is no longer active."
        )

    @jwt.expired_token_loader
    def _expired(_header: dict[str, Any], _payload: dict[str, Any]) -> Any:
        return problem_response(status=401, title="Unauthorized", detail="The token has expired.")

    @jwt.invalid_token_loader
    def _invalid(reason: str) -> Any:
        return problem_response(status=401, title="Unauthorized", detail=f"Invalid token: {reason}")

    @jwt.unauthorized_loader
    def _missing(reason: str) -> Any:
        return problem_response(
            status=401, title="Unauthorized", detail=f"Authentication required: {reason}"
        )

    app.extensions["vglpos_token_service"] = TokenService()
