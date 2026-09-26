"""Deployment defaults plus Redis-backed runtime feature overrides."""

from __future__ import annotations

import logging

from flask import current_app, has_app_context
from redis import Redis
from redis.exceptions import RedisError

from vglpos.services.exceptions import FeatureDisabledError

logger = logging.getLogger(__name__)

FEATURES: dict[str, str] = {
    "einvoice": "FEATURE_EINVOICE_ENABLED",
    "eway_bill": "FEATURE_EWAY_BILL_ENABLED",
    "report_jobs": "FEATURE_REPORT_JOBS_ENABLED",
}


def _key(name: str) -> str:
    if name not in FEATURES:
        raise ValueError(f"Unknown feature flag: {name}.")
    return f"vglpos:feature:{name}"


def _redis() -> Redis:
    return Redis.from_url(
        str(current_app.config["CACHE_REDIS_URL"]),
        socket_connect_timeout=0.25,
        socket_timeout=0.25,
        decode_responses=True,
    )


def feature_enabled(name: str) -> bool:
    """Read a shared override, degrading safely to the environment default."""
    config_key = FEATURES.get(name)
    if config_key is None:
        raise ValueError(f"Unknown feature flag: {name}.")
    if not has_app_context():
        # Domain services are also valid in migration/import tooling where no
        # Flask context exists; deployment defaults keep legacy behavior there.
        return True
    if current_app.testing or current_app.config["CACHE_TYPE"] == "SimpleCache":
        return bool(current_app.config[config_key])
    try:
        override = _redis().get(_key(name))
    except RedisError:
        logger.warning("feature_flag_store_unavailable", extra={"feature": name})
        override = None
    if override is None:
        return bool(current_app.config[config_key])
    return override == "1"


def require_feature(name: str) -> None:
    """Raise a typed 503 instead of partially running a disabled workflow."""
    if not feature_enabled(name):
        raise FeatureDisabledError(f"The {name} feature is temporarily disabled.")


def set_feature(name: str, enabled: bool) -> None:
    """Set a shared runtime override used by web and worker processes."""
    _redis().set(_key(name), "1" if enabled else "0")


def clear_feature(name: str) -> None:
    """Remove a runtime override and return to the deployment default."""
    _redis().delete(_key(name))
