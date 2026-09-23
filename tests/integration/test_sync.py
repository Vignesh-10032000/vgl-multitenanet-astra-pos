"""Integration gates for signed partial offline sync and catalogue deltas."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vglpos.domain.models import Sale
from vglpos.services.catalog_service import CatalogService
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    PaymentCommand,
)
from vglpos.services.sync_service import OfflineSyncService, SignedCheckoutOperation

from .conftest import ServiceContext, open_service_shift

SIGNING_SECRET = "integration-offline-signing-secret-value"


def _command(
    context: ServiceContext,
    identifier: UUID,
    quantity: str = "1.000",
    *,
    shift_id: int | None = None,
) -> CheckoutCommand:
    return CheckoutCommand(
        company_id=context.company.id,
        branch_id=context.branch.id,
        terminal_id=context.terminal.id,
        cashier_id=context.cashier.id,
        shift_id=shift_id,
        lines=[CheckoutLineCommand(context.product.id, quantity)],
        payments=[PaymentCommand("CASH", "118.00")],
        business_date=date(2026, 9, 21),
        offline_uuid=str(identifier),
    )


def _payload(
    context: ServiceContext,
    identifier: UUID,
    quantity: str = "1.000",
    *,
    shift_id: int | None = None,
) -> dict[str, object]:
    return {
        "lines": [
            {
                "product_id": context.product.id,
                "quantity": quantity,
                "line_discount": "0.00",
            }
        ],
        "payments": [{"method": "CASH", "amount": "118.00", "reference_number": None}],
        "customer_id": None,
        "business_date": "2026-09-21",
        "order_discount": "0.00",
        "apply_round_off": True,
        "shift_id": shift_id,
        "offline_uuid": str(identifier),
        "notes": None,
    }


def _service(session: Session, context: ServiceContext) -> OfflineSyncService:
    return OfflineSyncService(
        session,
        company_id=context.company.id,
        branch_id=context.branch.id,
        terminal_id=context.terminal.id,
        signing_secret=SIGNING_SECRET,
    )


def _signed_operation(
    service: OfflineSyncService,
    context: ServiceContext,
    identifier: UUID,
    quantity: str = "1.000",
    *,
    shift_id: int | None = None,
) -> SignedCheckoutOperation:
    payload = _payload(context, identifier, quantity, shift_id=shift_id)
    key = base64.urlsafe_b64decode(f"{service.bootstrap().signing_key}=")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    signature = (
        base64.urlsafe_b64encode(
            hmac.new(key, f"{identifier}.{body}".encode(), hashlib.sha256).digest()
        )
        .decode("ascii")
        .rstrip("=")
    )
    return SignedCheckoutOperation(
        identifier,
        _command(context, identifier, quantity, shift_id=shift_id),
        payload,
        signature,
    )


def test_duplicate_signed_uuid_creates_exactly_one_sale(
    service_session: Session, service_context: ServiceContext
) -> None:
    shift = open_service_shift(service_session, service_context)
    service = _service(service_session, service_context)
    identifier = uuid4()
    operation = _signed_operation(service, service_context, identifier, shift_id=shift.id)

    results = service.sync_batch([operation, operation])

    assert [result.status for result in results] == ["synced", "synced"]
    assert results[0].sale is not None and results[1].sale is not None
    assert results[0].sale.id == results[1].sale.id
    assert service_session.scalar(select(func.count()).select_from(Sale)) == 1


def test_partial_failure_keeps_rejected_bill_visible(
    service_session: Session, service_context: ServiceContext
) -> None:
    shift = open_service_shift(service_session, service_context)
    service = _service(service_session, service_context)
    good = _signed_operation(service, service_context, uuid4(), shift_id=shift.id)
    unavailable = _signed_operation(
        service, service_context, uuid4(), "2000.000", shift_id=shift.id
    )
    tampered = _signed_operation(service, service_context, uuid4(), shift_id=shift.id)
    tampered = SignedCheckoutOperation(
        tampered.uuid,
        tampered.command,
        tampered.payload,
        "A" * 43,
    )

    results = service.sync_batch([good, unavailable, tampered])

    assert results[0].status == "synced"
    assert results[1].status == "failed"
    assert results[1].error_type == "insufficient-stock"
    assert results[2].status == "failed"
    assert results[2].error_type == "invalid-offline-signature"
    assert service_session.scalar(select(func.count()).select_from(Sale)) == 1


def test_catalogue_delta_returns_only_rows_changed_after_watermark(
    service_session: Session, service_context: ServiceContext
) -> None:
    now = datetime.now(UTC)
    service_context.product.updated_at = now - timedelta(minutes=1)
    service_session.commit()

    delta = CatalogService(service_session, service_context.company.id).catalog_delta(
        since=now - timedelta(minutes=2),
        limit=100,
    )
    unchanged = CatalogService(service_session, service_context.company.id).catalog_delta(
        since=now,
        limit=100,
    )

    assert [record.product.id for record in delta.items] == [service_context.product.id]
    assert delta.items[0].tax_rate == service_context.tax_rate.rate
    assert unchanged.items == ()
