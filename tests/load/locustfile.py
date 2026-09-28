"""Phase 4 production-stack workload: search, five scans, quote, checkout."""

from __future__ import annotations

import os
from datetime import date
from itertools import count, cycle
from uuid import uuid4

from locust import HttpUser, between, events, task
from locust.env import Environment
from locust.exception import StopUser

from vglpos.performance_workload import lane_for_index

_lane_indices = count()


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for the load test.")
    return value


class CashierUser(HttpUser):
    wait_time = between(6, 6)

    def on_start(self) -> None:
        cashier_count = int(os.environ.get("PERF_CASHIER_COUNT", "1"))
        if cashier_count < 1:
            raise ValueError("PERF_CASHIER_COUNT must be positive.")
        lane = lane_for_index(
            next(_lane_indices) % cashier_count,
            cashier_count,
            username=_required_env("PERF_USERNAME"),
            first_branch_id=int(_required_env("PERF_BRANCH_ID")),
            first_terminal_id=int(_required_env("PERF_TERMINAL_ID")),
        )
        response = self.client.post(
            "/api/v1/auth/login",
            name="POST /api/v1/auth/login",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "company_code": _required_env("PERF_LOGIN_CODE"),
                "username": lane.username,
                "password": _required_env("PERF_PASSWORD"),
                "branch_id": lane.branch_id,
                "terminal_id": lane.terminal_id,
            },
        )
        if response.status_code != 200:
            raise StopUser()
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        barcodes = (
            lane.barcodes
            if cashier_count > 1
            else tuple(item.strip() for item in _required_env("PERF_BARCODES").split(","))
        )
        self.barcodes = cycle(barcodes)

    @task
    def complete_sale(self) -> None:
        self.client.get(
            "/api/v1/products?q=Benchmark&limit=20",
            name="GET /api/v1/products search",
            headers=self.headers,
        )
        lines: list[dict[str, str | int]] = []
        for _ in range(5):
            barcode = next(self.barcodes)
            with self.client.get(
                f"/api/v1/products/lookup?barcode={barcode}",
                name="GET /api/v1/products/lookup",
                headers=self.headers,
                catch_response=True,
            ) as response:
                if response.status_code != 200:
                    response.failure(f"barcode lookup returned {response.status_code}")
                    return
                lines.append({"product_id": response.json()["id"], "quantity": "1.000"})
        quote_payload = {
            "lines": lines,
            "business_date": date.today().isoformat(),
            "order_discount": "0.00",
            "apply_round_off": True,
        }
        with self.client.post(
            "/api/v1/sales/quote",
            name="POST /api/v1/sales/quote",
            headers={**self.headers, "Idempotency-Key": str(uuid4())},
            json=quote_payload,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"quote returned {response.status_code}")
                return
            net_amount = response.json()["net_amount"]
        self.client.post(
            "/api/v1/sales/checkout",
            name="POST /api/v1/sales/checkout",
            headers={**self.headers, "Idempotency-Key": str(uuid4())},
            json={
                **quote_payload,
                "payments": [{"method": "CASH", "amount": net_amount}],
            },
        )


@events.quitting.add_listener
def enforce_phase4_thresholds(environment: Environment, **_kwargs: object) -> None:
    total = environment.stats.total
    checkout = environment.stats.get("POST /api/v1/sales/checkout", "POST")
    checkout_p99 = checkout.get_response_time_percentile(0.99) or 0
    if total.fail_ratio > 0 or checkout.num_requests == 0 or checkout_p99 >= 1_000:
        environment.process_exit_code = 1
