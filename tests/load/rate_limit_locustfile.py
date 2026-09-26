"""Short distributed probe proving authentication limits return 429 under load."""

from __future__ import annotations

from uuid import uuid4

from locust import HttpUser, between, events, task
from locust.env import Environment

_limited_responses = 0
_server_errors = 0


@events.request.add_listener
def classify_response(*, response: object | None, **_kwargs: object) -> None:
    global _limited_responses, _server_errors
    status = int(getattr(response, "status_code", 0))
    if status == 429:
        _limited_responses += 1
    elif status >= 500:
        _server_errors += 1


class LoginProbe(HttpUser):
    wait_time = between(0.01, 0.03)

    @task
    def invalid_login(self) -> None:
        self.client.post(
            "/api/v1/auth/login",
            name="POST /api/v1/auth/login limited",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "company_code": "RATE-LIMIT-PROBE",
                "username": "probe",
                "password": "invalid-password",
            },
        )


@events.quitting.add_listener
def enforce_rate_limit(environment: Environment, **_kwargs: object) -> None:
    total = environment.stats.total
    if total.num_requests == 0 or _limited_responses == 0 or _server_errors > 0:
        environment.process_exit_code = 1
