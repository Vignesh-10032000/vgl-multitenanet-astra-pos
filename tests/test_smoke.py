"""Phase 1A infrastructure smoke tests.

These cover only the scaffold: health endpoint, request-id middleware,
RFC 7807 errors, security headers, the fail-closed endpoint guard, the
rollback fixture, and production config validation. No domain logic exists yet.
"""

from __future__ import annotations

import uuid

import pytest
from flask import Flask
from flask.testing import FlaskClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session, scoped_session

from vglpos.app import create_app
from vglpos.config import ProductionConfig, TestingConfig, get_config


def test_health_returns_200(client: FlaskClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["service"] == "vglpos"


def test_request_id_is_generated(client: FlaskClient) -> None:
    response = client.get("/health")
    request_id = response.headers.get("X-Request-Id")
    assert request_id
    uuid.UUID(request_id)  # generated ids must be valid UUIDs


def test_request_id_round_trips(client: FlaskClient) -> None:
    supplied = str(uuid.uuid4())
    response = client.get("/health", headers={"X-Request-Id": supplied})
    assert response.headers["X-Request-Id"] == supplied


def test_unknown_route_is_rfc7807(client: FlaskClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.content_type == "application/problem+json"
    body = response.get_json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["instance"] == "/does-not-exist"
    assert body["request_id"]


def test_security_headers_present_without_unsafe_inline(client: FlaskClient) -> None:
    response = client.get("/health")
    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_undeclared_endpoint_is_refused() -> None:
    """Rule 5 guard: a route not in PUBLIC_ENDPOINTS (and, for now, without a
    permission decorator) must be rejected, not silently served."""
    app = create_app(TestingConfig)

    @app.get("/undeclared")
    def undeclared() -> str:
        return "should never be reachable"

    response = app.test_client().get("/undeclared")
    assert response.status_code == 403
    assert response.content_type == "application/problem+json"


def test_db_session_executes_inside_savepoint_transaction(
    db_session: scoped_session[Session],
) -> None:
    assert db_session.execute(text("SELECT 1")).scalar_one() == 1
    db_session.commit()  # must only release the savepoint, never escape the fixture
    assert db_session.execute(text("SELECT 1")).scalar_one() == 1


def test_production_config_refuses_missing_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("SECRET_KEY", "JWT_SECRET_KEY", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValidationError):
        ProductionConfig(_env_file=None)


def test_production_config_refuses_known_default_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "dev-only-secret-key-not-for-production")
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://vglpos:vglpos@localhost:5432/vglpos_dev"
    )
    with pytest.raises(ValidationError):
        ProductionConfig(_env_file=None)


def test_production_config_accepts_strong_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "k" * 48)
    monkeypatch.setenv("JWT_SECRET_KEY", "j" * 48)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://pos:example-strong-password@db.internal:5432/pos"
    )
    config = ProductionConfig(_env_file=None)
    assert config.DEBUG is False
    assert config.TESTING is False


def test_get_config_rejects_unknown_env() -> None:
    with pytest.raises(RuntimeError):
        get_config("staging-typo")


def test_testing_config_ignores_database_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """DATABASE_URL must never leak into a test run; only TEST_DATABASE_URL counts."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pos:secret@db.internal:5432/pos")
    config = TestingConfig(_env_file=None)
    assert config.DATABASE_URL == "sqlite+pysqlite:///:memory:"


def test_testing_config_ignores_non_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer's runtime variables must not make the hermetic test app invalid."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "release")
    monkeypatch.setenv("SECRET_KEY", "runtime-secret-that-tests-must-not-use")

    config = TestingConfig()

    assert config.APP_ENV == "testing"
    assert config.DEBUG is False
    assert config.SECRET_KEY == "testing-only-secret-key-not-for-production"


def test_p1a_1_health_survives_redis_outage() -> None:
    """P1A-1: with rate limiting enabled and Redis unreachable, requests must
    degrade to the in-memory fallback (and still carry a request_id), not 500."""

    class RedisDownConfig(TestingConfig):
        RATELIMIT_ENABLED: bool = True
        REDIS_URL: str = "redis://127.0.0.1:1/0"  # nothing listens on port 1

    app = create_app(RedisDownConfig)
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.headers["X-Request-Id"]


def test_app_has_no_module_level_instance() -> None:
    """The factory rule: importing vglpos.app must never yield an app object."""
    import vglpos.app as app_module

    assert not any(isinstance(value, Flask) for value in vars(app_module).values())
