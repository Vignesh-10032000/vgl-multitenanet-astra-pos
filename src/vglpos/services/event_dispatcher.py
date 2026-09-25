"""Synchronous post-commit domain-event subscribers."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from vglpos.domain.events import ProductUpdated, SaleCompleted, SaleUpdated
from vglpos.extensions import db
from vglpos.services.cache_service import invalidate_catalogue, invalidate_dashboard
from vglpos.services.einvoice_service import EInvoiceService
from vglpos.tasks.compliance import process_einvoice

logger = logging.getLogger(__name__)

DomainEvent = ProductUpdated | SaleCompleted | SaleUpdated


def publish_event(event: DomainEvent) -> None:
    """Apply lightweight cache invalidation after the owning transaction commits."""
    if isinstance(event, ProductUpdated):
        invalidate_catalogue(event.company_id)
    else:
        invalidate_dashboard(event.company_id, event.branch_id)
    if isinstance(event, SaleCompleted):
        try:
            with Session(db.engine) as session:
                record = EInvoiceService(session, event.company_id).queue_sale(event.sale_id)
            if record is not None and record.status == "PENDING":
                process_einvoice.delay(company_id=event.company_id, record_id=record.id)
        except Exception:
            # The invoice is already committed. Persisted reconciliation detects missing
            # records, while this exception log alerts operations without blocking the bill.
            logger.exception(
                "e_invoice_enqueue_failed",
                extra={"company_id": event.company_id, "sale_id": event.sale_id},
            )
