"""Security gates that exercise controls rather than only inspecting configuration."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from vglpos.app import create_app
from vglpos.config import TestingConfig


def test_login_rate_limit_returns_429() -> None:
    class RateLimitedConfig(TestingConfig):
        RATELIMIT_ENABLED: bool = True
        REDIS_URL: str = "memory://"

    client = create_app(RateLimitedConfig).test_client()
    responses = [
        client.post(
            "/api/v1/auth/login",
            headers={"Idempotency-Key": str(uuid4())},
            json={},
        )
        for _ in range(6)
    ]
    assert all(response.status_code != 429 for response in responses[:5])
    assert responses[5].status_code == 429


def test_application_role_cannot_update_audit_log() -> None:
    owner_url = os.environ.get("SECURITY_DATABASE_OWNER_URL", "")
    if not owner_url:
        pytest.skip("SECURITY_DATABASE_OWNER_URL is required for PostgreSQL privilege test.")
    with (
        psycopg.connect(owner_url, autocommit=True) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SET ROLE vglpos_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            cursor.execute("UPDATE audit_log SET action = action WHERE false")
        assert exc_info.value.sqlstate == "42501"
