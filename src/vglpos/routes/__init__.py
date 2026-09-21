"""Blueprint registry and the public-endpoint allowlist."""

from __future__ import annotations

from flask import Blueprint

from vglpos.api.v1.auth import auth_bp
from vglpos.api.v1.customers import customers_bp
from vglpos.api.v1.openapi import openapi_bp
from vglpos.api.v1.products import products_bp
from vglpos.api.v1.reports import reports_bp
from vglpos.api.v1.sales import sales_bp
from vglpos.api.v1.settings import settings_bp
from vglpos.api.v1.shifts import shifts_bp
from vglpos.api.v1.sync import sync_bp
from vglpos.routes.health import health_bp
from vglpos.web.routes import web_bp

# Every blueprint the factory registers. New blueprints are added here, never
# ad hoc inside create_app, so the route surface is reviewable in one place.
BLUEPRINTS: tuple[Blueprint, ...] = (
    health_bp,
    auth_bp,
    sales_bp,
    products_bp,
    customers_bp,
    shifts_bp,
    reports_bp,
    sync_bp,
    settings_bp,
    openapi_bp,
    web_bp,
)

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
        # Browser routes render data-free application shells. All tenant data
        # still crosses permission-protected /api/v1 endpoints with a JWT.
        "web.login",
        "web.dashboard",
        "web.pos",
        "web.products",
        "web.customers",
        "web.sales",
        "web.reports",
        "web.settings",
        "web.receipt",
        "web.offline_receipt",
        "web.sync_queue",
        # PWA metadata and worker code contain no tenant data. They must remain
        # fetchable by the browser outside an authenticated fetch context.
        "web.web_manifest",
        "web.pwa_assets",
        "web.service_worker",
    }
)
