"""Privacy and feature-control regression tests for production operations."""

from __future__ import annotations

from flask import Flask

from vglpos.app import create_app
from vglpos.config import TestingConfig
from vglpos.observability import scrub_sentry_event
from vglpos.services.feature_flags import feature_enabled


def test_sentry_event_scrubs_customer_identifiers_recursively() -> None:
    event = {
        "message": "Customer 9876543210 used 33AACCC1234A1Z5",
        "request": {
            "headers": {"Authorization": "Bearer secret", "X-Safe": "yes"},
            "data": {
                "customer_name": "Priya",
                "phone": "9876543210",
                "access_token": "access-secret",
                "client_secret": "client-secret",
                "profile": {"name": "Priya", "email": "customer@example.test"},
            },
        },
    }

    scrubbed = scrub_sentry_event(event, {})

    assert scrubbed["message"] == "Customer [Filtered phone] used [Filtered GSTIN]"
    request = scrubbed["request"]
    assert isinstance(request, dict)
    assert request["headers"]["Authorization"] == "[Filtered]"
    assert request["data"]["customer_name"] == "[Filtered]"
    assert request["data"]["phone"] == "[Filtered]"
    assert request["data"]["access_token"] == "[Filtered]"
    assert request["data"]["client_secret"] == "[Filtered]"
    assert request["data"]["profile"]["name"] == "[Filtered]"
    assert request["data"]["profile"]["email"] == "[Filtered]"


def test_feature_flags_use_safe_test_defaults() -> None:
    class DisabledFeatures(TestingConfig):
        FEATURE_EINVOICE_ENABLED: bool = False

    app: Flask = create_app(DisabledFeatures)
    with app.app_context():
        assert feature_enabled("einvoice") is False
        assert feature_enabled("report_jobs") is True


def test_metrics_endpoint_requires_configured_bearer_token() -> None:
    class ProtectedMetrics(TestingConfig):
        METRICS_AUTH_TOKEN: str = "test-only-metrics-token"

    client = create_app(ProtectedMetrics).test_client()
    assert client.get("/metrics").status_code == 401
    response = client.get("/metrics", headers={"Authorization": "Bearer test-only-metrics-token"})
    assert response.status_code == 200
