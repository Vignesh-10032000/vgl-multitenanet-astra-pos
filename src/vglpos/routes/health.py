"""Liveness endpoint."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from vglpos import __version__

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health() -> tuple[Response, int]:
    """Liveness probe for load balancers, the Docker healthcheck and CI.

    WHY no database/Redis checks here: liveness must not turn an infrastructure
    outage into a cascade of worker restarts. Dependency-aware readiness is a
    separate endpoint that arrives with the operations phase.
    """
    return jsonify({"status": "ok", "service": "vglpos", "version": __version__}), 200
