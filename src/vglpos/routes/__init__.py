"""Blueprint registry and the public-endpoint allowlist."""

from __future__ import annotations

from flask import Blueprint

from vglpos.routes.auth import auth_bp
from vglpos.routes.health import health_bp

# Every blueprint the factory registers. New blueprints are added here, never
# ad hoc inside create_app, so the route surface is reviewable in one place.
BLUEPRINTS: tuple[Blueprint, ...] = (health_bp, auth_bp)

# Rule 5: endpoints listed here are the ONLY ones served without a permission
# decorator. Each entry documents why it is genuinely public.
PUBLIC_ENDPOINTS: frozenset[str] = frozenset(
    {
        # Unauthenticated liveness probe: load balancers, the Docker healthcheck
        # and the CI gate must reach it before any auth infrastructure exists.
        "health.health",
        # Credential entry and refresh-token rotation must be reachable before
        # an access token exists; each endpoint enforces its own rate/JWT checks.
        "auth.login",
        "auth.pin_login",
        "auth.refresh",
        # Flask's built-in static-file endpoint: assets contain no data and must
        # load on the login page, i.e. before any session exists.
        "static",
    }
)
