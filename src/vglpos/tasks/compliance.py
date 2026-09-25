"""Resilient Celery jobs for e-invoices, e-way bills, and queue monitoring."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from secrets import randbelow
from urllib.request import Request, urlopen

from celery import Task
from flask import current_app
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import Company, EInvoice, EWayBill
from vglpos.extensions import celery, db
from vglpos.services.einvoice_service import EInvoiceService, EWayBillService
from vglpos.services.irp_client import IRPTransientError, configured_irp_client

logger = logging.getLogger(__name__)


@celery.task(bind=True, name="vglpos.process_einvoice", max_retries=20)
def process_einvoice(self: Task, *, company_id: int, record_id: int) -> dict[str, int | str]:
    """Generate or cancel an IRN with exponential backoff and bounded jitter."""
    with Session(db.engine) as session:
        record = EInvoiceService(session, company_id).process(record_id, configured_irp_client())
        if record.status in {"RETRY", "CANCEL_RETRY"}:
            delay = max(
                1,
                int((record.next_attempt_at or datetime.now(UTC)).timestamp())
                - int(datetime.now(UTC).timestamp()),
            ) + randbelow(31)
            raise self.retry(
                exc=IRPTransientError(record.error_text or "IRP retry scheduled."),
                countdown=delay,
                max_retries=max(0, record.max_attempts - 1),
            )
        return {"record_id": record.id, "status": record.status}


@celery.task(bind=True, name="vglpos.process_eway_bill", max_retries=20)
def process_eway_bill(self: Task, *, company_id: int, record_id: int) -> dict[str, int | str]:
    """Generate an e-way bill with the same durable retry policy as e-invoices."""
    with Session(db.engine) as session:
        record = EWayBillService(session, company_id).process(record_id, configured_irp_client())
        if record.status == "RETRY":
            delay = max(
                1,
                int((record.next_attempt_at or datetime.now(UTC)).timestamp())
                - int(datetime.now(UTC).timestamp()),
            ) + randbelow(31)
            raise self.retry(
                exc=IRPTransientError(record.error_text or "E-way bill retry scheduled."),
                countdown=delay,
                max_retries=max(0, record.max_attempts - 1),
            )
        return {"record_id": record.id, "status": record.status}


@celery.task(name="vglpos.reconcile_einvoices")
def reconcile_einvoices() -> dict[str, int | str]:
    """Backfill missing queue rows and re-dispatch due retries for every enabled tenant."""
    queued = 0
    retried = 0
    now = datetime.now(UTC)
    with Session(db.engine) as session:
        companies = tuple(
            session.execute(
                select(
                    Company.id,
                    Company.e_invoice_enabled,
                    Company.composition_scheme_enabled,
                ).where(Company.deleted_at.is_(None))
            )
        )
    for company_id, e_invoice_enabled, composition_scheme_enabled in companies:
        with Session(db.engine) as session:
            service = EInvoiceService(session, company_id)
            service.recover_stale_processing(now=now)
            EWayBillService(session, company_id).recover_stale_processing(now=now)
            if e_invoice_enabled and not composition_scheme_enabled:
                for issue in service.reconciliation():
                    if issue.issue != "MISSING":
                        continue
                    record = service.queue_sale(issue.sale_id)
                    if record is not None and record.status == "PENDING":
                        process_einvoice.delay(company_id=company_id, record_id=record.id)
                        queued += 1
            due = tuple(
                session.scalars(
                    select(EInvoice).where(
                        EInvoice.company_id == company_id,
                        EInvoice.status.in_(("RETRY", "CANCEL_RETRY")),
                        EInvoice.next_attempt_at <= now,
                        EInvoice.deleted_at.is_(None),
                    )
                )
            )
            for record in due:
                process_einvoice.delay(company_id=company_id, record_id=record.id)
                retried += 1
            due_eway_bills = tuple(
                session.scalars(
                    select(EWayBill).where(
                        EWayBill.company_id == company_id,
                        EWayBill.status == "RETRY",
                        EWayBill.next_attempt_at <= now,
                        EWayBill.deleted_at.is_(None),
                    )
                )
            )
            for eway_record in due_eway_bills:
                process_eway_bill.delay(company_id=company_id, record_id=eway_record.id)
                retried += 1
    return {"status": "reconciled", "queued": queued, "retried": retried}


@celery.task(name="vglpos.monitor_compliance_queue")
def monitor_compliance_queue() -> dict[str, int | str]:
    """Emit a configurable webhook alert for queue pressure, age, or dead letters."""
    alerts: list[dict[str, object]] = []
    with Session(db.engine) as session:
        company_ids = tuple(
            session.scalars(
                select(Company.id).where(
                    Company.e_invoice_enabled.is_(True), Company.deleted_at.is_(None)
                )
            )
        )
        for company_id in company_ids:
            alert = EInvoiceService(session, company_id).alert()
            if alert.active:
                alerts.append(
                    {
                        "company_id": company_id,
                        "pending_count": alert.pending_count,
                        "dead_letter_count": alert.dead_letter_count,
                        "oldest_pending_at": (
                            alert.oldest_pending_at.isoformat()
                            if alert.oldest_pending_at is not None
                            else None
                        ),
                        "exceeds_queue_limit": alert.exceeds_queue_limit,
                        "exceeds_reporting_window": alert.exceeds_reporting_window,
                    }
                )
    if alerts:
        logger.warning("compliance_queue_alert", extra={"alerts": alerts})
        _send_alert(alerts)
    return {"status": "checked", "alert_count": len(alerts)}


def _send_alert(alerts: list[dict[str, object]]) -> None:
    """Notify the deployment-selected operations channel without hardcoded endpoints."""
    url = str(current_app.config["COMPLIANCE_ALERT_WEBHOOK_URL"]).strip()
    token = str(current_app.config["COMPLIANCE_ALERT_API_TOKEN"]).strip()
    if not url:
        return
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        data=json.dumps({"alerts": alerts}, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            if not 200 <= response.status < 300:
                raise OSError(f"Compliance alert webhook returned HTTP {response.status}.")
    except OSError:
        logger.exception("compliance_alert_delivery_failed")
