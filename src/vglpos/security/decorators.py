"""JWT authorization boundary for every non-public API endpoint."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar, cast

import structlog
from flask import g, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from vglpos.extensions import db
from vglpos.security.audit import record_audit_event, set_audit_context
from vglpos.security.permissions import KNOWN_PERMISSION_CODES
from vglpos.security.tokens import TokenService
from vglpos.services.exceptions import AuthenticationError, AuthorizationError, SessionLockedError

P = ParamSpec("P")
R = TypeVar("R")

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def _audit_denial(*, company_id: int, user_id: int, required: tuple[str, ...], reason: str) -> None:
    try:
        with Session(db.engine) as session:
            set_audit_context(
                session,
                user_id=user_id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string,
                request_id=getattr(g, "request_id", None),
            )
            record_audit_event(
                session,
                company_id=company_id,
                user_id=user_id,
                action="PERMISSION_DENIED",
                entity_type="Endpoint",
                entity_id=request.endpoint or request.path,
                new_values={
                    "required": list(required),
                    "path": request.path,
                    "method": request.method,
                    "reason": reason,
                },
            )
            session.commit()
    except SQLAlchemyError:
        logger.exception(
            "permission_denial_audit_failed",
            company_id=company_id,
            user_id=user_id,
            path=request.path,
        )


def require_permission(
    *codes: str, require_all: bool = False
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Require verified JWT claims and one or all declared permission codes."""
    unknown = set(codes) - KNOWN_PERMISSION_CODES
    if unknown:
        raise RuntimeError(f"Unknown permission code(s): {', '.join(sorted(unknown))}")

    def decorator(view: Callable[P, R]) -> Callable[P, R]:
        @wraps(view)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            verify_jwt_in_request()
            claims = get_jwt()
            try:
                user_id = int(get_jwt_identity())
                company_id = int(claims["company_id"])
                branch_id = (
                    int(claims["branch_id"]) if claims.get("branch_id") is not None else None
                )
                terminal_id = (
                    int(claims["terminal_id"]) if claims.get("terminal_id") is not None else None
                )
                raw_permissions = claims.get("permissions", [])
                if not isinstance(raw_permissions, list) or not all(
                    isinstance(code, str) for code in raw_permissions
                ):
                    raise TypeError
                permissions = frozenset(raw_permissions)
            except (KeyError, TypeError, ValueError) as exc:
                raise AuthenticationError("The access token is missing required claims.") from exc
            if not permissions <= KNOWN_PERMISSION_CODES:
                raise AuthenticationError("The access token contains an unknown permission.")

            g.user_id = user_id
            g.company_id = company_id
            g.branch_id = branch_id
            g.terminal_id = terminal_id
            structlog.contextvars.bind_contextvars(
                user_id=user_id,
                company_id=company_id,
                branch_id=branch_id,
                terminal_id=terminal_id,
            )
            if TokenService.is_screen_locked(claims):
                _audit_denial(
                    company_id=company_id,
                    user_id=user_id,
                    required=codes,
                    reason="screen_locked",
                )
                raise SessionLockedError("The counter screen is locked; sign in with the PIN.")
            allowed = (
                all(code in permissions for code in codes)
                if require_all
                else not codes or any(code in permissions for code in codes)
            )
            if not allowed:
                logger.warning(
                    "permission_denied",
                    user_id=user_id,
                    company_id=company_id,
                    path=request.path,
                    required=codes,
                )
                _audit_denial(
                    company_id=company_id,
                    user_id=user_id,
                    required=codes,
                    reason="missing_permission",
                )
                raise AuthorizationError("The current user does not have permission.")
            return view(*args, **kwargs)

        wrapped.__dict__["_permission_required"] = True
        wrapped.__dict__["_permission_codes"] = codes
        return cast(Callable[P, R], wrapped)

    return decorator
