"""Scheduled database summary refresh and counter reconciliation tasks."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from vglpos.domain.models import Company
from vglpos.extensions import celery, db
from vglpos.services.customer_reconciliation import CustomerCounterReconciliationService


@celery.task(name="vglpos.refresh_daily_sales_summary")
def refresh_daily_sales_summary() -> dict[str, str]:
    """Refresh the PostgreSQL dashboard view without blocking readers."""
    if db.engine.dialect.name != "postgresql":
        return {"status": "skipped", "reason": "materialized view is PostgreSQL-only"}
    with db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_sales_summary"))
    return {"status": "refreshed"}


@celery.task(name="vglpos.reconcile_customer_counters")
def reconcile_customer_counters() -> dict[str, int | str]:
    """Repair counter drift across every active company once per night."""
    drift_count = 0
    with Session(db.engine) as session:
        company_ids = tuple(session.scalars(select(Company.id).where(Company.deleted_at.is_(None))))
        for company_id in company_ids:
            drift_count += len(
                CustomerCounterReconciliationService(session, company_id).reconcile(apply=True)
            )
    return {"status": "reconciled", "drift_count": drift_count}
