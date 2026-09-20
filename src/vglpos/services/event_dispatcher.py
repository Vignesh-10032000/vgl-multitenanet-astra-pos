"""Synchronous post-commit domain-event subscribers."""

from __future__ import annotations

from vglpos.domain.events import ProductUpdated, SaleCompleted, SaleUpdated
from vglpos.services.cache_service import invalidate_catalogue, invalidate_dashboard

DomainEvent = ProductUpdated | SaleCompleted | SaleUpdated


def publish_event(event: DomainEvent) -> None:
    """Apply lightweight cache invalidation after the owning transaction commits."""
    if isinstance(event, ProductUpdated):
        invalidate_catalogue(event.company_id)
    else:
        invalidate_dashboard(event.company_id, event.branch_id)
