"""Liveness endpoint."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from vglpos import __version__
from vglpos.extensions import db
from vglpos.observability import metrics_authorized, prometheus_response

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health() -> tuple[Response, int]:
    """Liveness probe for load balancers, the Docker healthcheck and CI.

    WHY no database/Redis checks here: liveness must not turn an infrastructure
    outage into a cascade of worker restarts. Dependency-aware readiness is a
    separate endpoint that arrives with the operations phase.
    """
    return jsonify({"status": "ok", "service": "vglpos", "version": __version__}), 200


@health_bp.get("/ready")
def ready() -> tuple[Response, int]:
    """Dependency-aware probe used to gate deployment traffic."""
    checks: dict[str, str] = {}
    try:
        with Session(db.engine) as session:
            session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    if current_app.testing or current_app.config["CACHE_TYPE"] == "SimpleCache":
        checks["redis"] = "not-required"
    else:
        try:
            Redis.from_url(
                str(current_app.config["CACHE_REDIS_URL"]),
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            ).ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
    status = 200 if all(value in {"ok", "not-required"} for value in checks.values()) else 503
    return jsonify({"status": "ready" if status == 200 else "not-ready", "checks": checks}), status


@health_bp.get("/metrics")
def metrics() -> Response:
    """Prometheus scrape endpoint protected by a deployment-owned bearer token."""
    if not metrics_authorized():
        return Response(status=401, headers={"WWW-Authenticate": "Bearer"})
    return prometheus_response()
