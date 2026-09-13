"""Blueprint registry and the public-endpoint allowlist."""

from __future__ import annotations

from flask import Blueprint

from vglpos.routes.health import health_bp

# Every blueprint the factory registers. New blueprints are added here, never
# ad hoc inside create_app, so the route surface is reviewable in one place.
BLUEPRINTS: tuple[Blueprint, ...] = (health_bp,)

# Rule 5: endpoints listed here are the ONLY ones served without a permission
# decorator. Each entry documents why it is genuinely public.
PUBLIC_ENDPOINTS: frozenset[str] = frozenset(
    {
        # Unauthenticated liveness probe: load balancers, the Docker healthcheck
        # and the CI gate must reach it before any auth infrastructure exists.
        "health.health",
        # Flask's built-in static-file endpoint: assets contain no data and must
        # load on the login page, i.e. before any session exists.
        "static",
    }
)
