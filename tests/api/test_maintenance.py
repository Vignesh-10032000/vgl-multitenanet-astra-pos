"""Maintenance command and scheduled-task registration."""

from __future__ import annotations

from flask import Flask

from tests.api.conftest import IdentityContext
from vglpos.tasks.maintenance import refresh_daily_sales_summary


def test_counter_reconciliation_cli_is_registered(
    api_app: Flask,
    api_identity: IdentityContext,
) -> None:
    result = api_app.test_cli_runner().invoke(
        args=[
            "reconcile-customer-counters",
            "--company-id",
            str(api_identity.company.id),
            "--check-only",
        ]
    )
    assert result.exit_code == 0, result.output
    assert "0 drift row(s) reported" in result.output


def test_maintenance_tasks_are_scheduled_and_sqlite_refresh_is_safe(api_app: Flask) -> None:
    schedule = api_app.config["CELERY"]["beat_schedule"]
    assert schedule["refresh-daily-sales-summary"]["schedule"] == 300.0
    assert schedule["reconcile-customer-counters-nightly"]["task"] == (
        "vglpos.reconcile_customer_counters"
    )
    with api_app.app_context():
        assert refresh_daily_sales_summary.run()["status"] == "skipped"
