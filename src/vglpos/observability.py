"""Production telemetry with privacy-safe error reporting and Prometheus metrics."""

from __future__ import annotations

import hmac
import logging
import math
import os
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal
from threading import Lock
from time import perf_counter
from typing import Any

import sentry_sdk
from flask import Flask, Response, current_app, g, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram
from prometheus_client.exposition import generate_latest
from prometheus_client.multiprocess import MultiProcessCollector
from prometheus_client.registry import CollectorRegistry
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vglpos.domain.models import EInvoice
from vglpos.extensions import db

logger = logging.getLogger(__name__)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency by stable Flask route.",
    ("route", "method", "status"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
CHECKOUT_TOTAL = Counter("checkout_total", "Successfully committed checkouts.")
CHECKOUT_FAILURES = Counter(
    "checkout_failures_total", "Checkout failures by stable reason.", ("reason",)
)
CHECKOUT_REVENUE = Gauge(
    "checkout_revenue_rupees_total",
    "Committed checkout revenue in rupees.",
    multiprocess_mode="sum",
)
OFFLINE_QUEUE_DEPTH = Gauge(
    "offline_queue_depth",
    "Offline checkout operations currently being synchronized.",
    multiprocess_mode="livesum",
)
EINVOICE_PENDING = Gauge(
    "einvoice_pending_total",
    "E-invoices waiting, retrying, or currently processing.",
    multiprocess_mode="mostrecent",
)
SHIFT_VARIANCE = Gauge(
    "shift_variance_rupees",
    "Absolute variance at the most recently closed shift.",
    multiprocess_mode="mostrecent",
)
DB_POOL_IN_USE = Gauge(
    "db_pool_in_use",
    "Checked-out database pool connections.",
    multiprocess_mode="livesum",
)

_CHECKOUT_REVENUE_VALUE = Decimal("0")
_CHECKOUT_REVENUE_LOCK = Lock()

_SENSITIVE_KEYS = frozenset(
    {
        "address",
        "address_line1",
        "address_line2",
        "city",
        "contact_email",
        "contact_person",
        "contact_phone",
        "email",
        "full_name",
        "gstin",
        "legal_name",
        "name",
        "pan",
        "phone",
        "phone_number",
        "postal_code",
        "mobile",
        "mobile_number",
        "customer_name",
        "customer",
        "authorization",
        "cookie",
        "set-cookie",
        "password",
        "token",
        "secret",
    }
)
_SENSITIVE_KEY_FRAGMENTS = (
    "authorization",
    "cookie",
    "credential",
    "customer",
    "gstin",
    "mobile",
    "password",
    "phone",
    "secret",
    "token",
)
_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?91[- ]?)?[6-9]\d{9}(?!\d)")


def _scrub(value: Any, key: str = "") -> Any:
    """Recursively redact known identifiers without changing event topology."""
    normalized_key = key.lower().replace("-", "_")
    if normalized_key in _SENSITIVE_KEYS or any(
        fragment in normalized_key for fragment in _SENSITIVE_KEY_FRAGMENTS
    ):
        return "[Filtered]"
    if isinstance(value, Mapping):
        return {str(item_key): _scrub(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub(item) for item in value)
    if isinstance(value, str):
        return _PHONE.sub("[Filtered phone]", _GSTIN.sub("[Filtered GSTIN]", value))
    return value


def scrub_sentry_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Sentry ``before_send`` hook; intentionally exported for regression tests."""
    scrubbed = _scrub(event)
    assert isinstance(scrubbed, dict)
    return scrubbed


def init_sentry(app: Flask) -> None:
    """Enable Sentry only when a deployment explicitly supplies a DSN."""
    dsn = str(app.config.get("SENTRY_DSN", "")).strip()
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=str(app.config["SENTRY_ENVIRONMENT"]),
        traces_sample_rate=app.config["SENTRY_TRACES_SAMPLE_RATE"],
        send_default_pii=False,
        max_request_body_size="never",
        before_send=scrub_sentry_event,
    )


def register_request_metrics(app: Flask) -> None:
    """Observe every request with bounded-cardinality labels."""

    @app.before_request
    def _start_request_timer() -> None:
        g.request_started_at = perf_counter()

    @app.after_request
    def _observe_request(response: Response) -> Response:
        started = getattr(g, "request_started_at", None)
        if started is not None:
            rule = request.url_rule.rule if request.url_rule is not None else "unmatched"
            HTTP_REQUEST_DURATION.labels(rule, request.method, str(response.status_code)).observe(
                perf_counter() - started
            )
        return response


def record_checkout_success(amounts: Iterable[Decimal]) -> None:
    """Record committed checkout counts while keeping monetary state as Decimal."""
    committed = tuple(amounts)
    if not committed:
        return
    CHECKOUT_TOTAL.inc(len(committed))
    revenue = sum(committed, Decimal("0"))
    global _CHECKOUT_REVENUE_VALUE
    with _CHECKOUT_REVENUE_LOCK:
        _CHECKOUT_REVENUE_VALUE += revenue
        CHECKOUT_REVENUE.set(_CHECKOUT_REVENUE_VALUE)


def record_shift_variance(amount: Decimal) -> None:
    """Expose the latest absolute variance without changing its Decimal representation."""
    SHIFT_VARIANCE.set(abs(amount))


def metrics_authorized() -> bool:
    """Authenticate the internal scrape endpoint with a constant-time comparison."""
    expected = str(current_app.config.get("METRICS_AUTH_TOKEN", ""))
    if current_app.testing and not expected:
        return True
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
    return bool(expected) and hmac.compare_digest(supplied, expected)


def _refresh_gauges() -> None:
    try:
        pool = db.engine.pool
        checkedout = getattr(pool, "checkedout", None)
        if callable(checkedout):
            DB_POOL_IN_USE.set(checkedout())
        with Session(db.engine) as session:
            count = session.scalar(
                select(func.count(EInvoice.id)).where(
                    EInvoice.status.in_(("PENDING", "RETRY", "PROCESSING")),
                    EInvoice.deleted_at.is_(None),
                )
            )
            EINVOICE_PENDING.set(count or 0)
    except Exception:
        # Scraping must remain useful during the very database outage it diagnoses.
        logger.warning("metrics_dependency_refresh_failed", exc_info=True)
        DB_POOL_IN_USE.set(math.nan)
        EINVOICE_PENDING.set(math.nan)


def prometheus_response() -> Response:
    """Render process or Gunicorn multiprocess metrics."""
    _refresh_gauges()
    multiprocess_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if multiprocess_dir:
        registry = CollectorRegistry()
        MultiProcessCollector(registry)
        payload = generate_latest(registry)
    else:
        payload = generate_latest()
    return Response(payload, status=200, content_type=CONTENT_TYPE_LATEST)
